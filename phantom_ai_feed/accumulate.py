"""Accumulate fresh feed entries into the phantom FTS5 store (conditional fetch).

This is the first-class capture path: it ties ``fetch`` (conditional GET) to
``capture`` (FTS5) so the local knowledge base GROWS over time, cheaply.

  load validator cache
    -> fetch_all(feeds, cache=cache)          # conditional GET per feed
       - HTTP 200  -> entries captured into FTS5, validator refreshed
       - HTTP 304  -> NotModified, feed SKIPPED (no re-download, no re-capture)
       - error     -> counted and skipped
    -> save validator cache                    # next run asks "changed since?"

Why this — not the daily digest — is the right home for conditional GET: the
digest re-renders each feed's latest N every day, so a 304 there would blank an
unchanged section. Accumulation only ever ADDS, so "nothing changed -> capture
nothing" is exactly correct and saves the bandwidth + capture work.

Honest scope: conditional GET dedupes at the FEED level (a whole unchanged feed
is skipped). Entry-level idempotency WITHIN a changed feed — the top-N overlap
day to day — is not handled here; FTS5 capture is append-only, so a changed feed
may re-capture entries it captured before. That is a separate follow-up.

CLI:
  python -m phantom_ai_feed.accumulate            # capture into ~/.phantom-mesh
  python -m phantom_ai_feed.accumulate --strict   # core feeds only
  python -m phantom_ai_feed.accumulate --dry-run  # build capture cmds, no write
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from . import capture as _capture
from . import dedup as _dedup
from . import fetch as _fetch

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS = REPO_ROOT / "sources" / "feeds.toml"
DEFAULT_CACHE = (
    Path.home() / ".phantom-mesh" / "logs" / "phantom-ai-feed" / "fetch-cache.json"
)
DEFAULT_SEEN = (
    Path.home() / ".phantom-mesh" / "logs" / "phantom-ai-feed" / "seen-entries.json"
)

# Per-feed cap on remembered entry keys. A feed only ever surfaces its most
# recent items, so an entry that scrolls off the window long ago won't reappear;
# bounding the seen-list keeps the store from growing without limit.
MAX_SEEN_PER_FEED = 200


@dataclass
class AccumulateResult:
    """Per-run tally.

    - ``changed``        feeds that returned new content (HTTP 200)
    - ``unchanged``      feeds skipped via HTTP 304 (NotModified)
    - ``errored``        feeds whose fetch failed
    - ``captured``         entries successfully written into FTS5
    - ``capture_failed``   entries whose capture failed (e.g. no phantom CLI)
    - ``skipped_duplicate`` entries skipped as already-seen for that feed
    """

    changed: int = 0
    unchanged: int = 0
    errored: int = 0
    captured: int = 0
    capture_failed: int = 0
    skipped_duplicate: int = 0

    @property
    def total_feeds(self) -> int:
        return self.changed + self.unchanged + self.errored


def run(
    feeds_toml: Path = DEFAULT_FEEDS,
    *,
    cache_path: Path = DEFAULT_CACHE,
    seen_path: Path | None = None,
    top_n: int = 3,
    strict: bool = False,
    dry_run: bool = False,
) -> AccumulateResult:
    feeds = _fetch.filter_feeds(_fetch.load_feeds(feeds_toml), strict=strict)
    if not feeds:
        raise SystemExit(f"no [[feed]] entries in {feeds_toml}")

    seen_path = Path(seen_path) if seen_path else Path(cache_path).parent / "seen-entries.json"

    cache = _fetch.load_feed_cache(cache_path)
    # Snapshot validators BEFORE fetch_all mutates the cache in place, so a feed
    # whose entries fail to capture can be rolled back to its prior validator
    # (or dropped) — otherwise next run's 304 would skip entries that never
    # actually reached FTS5.
    prior = {k: dict(v) for k, v in cache.items() if isinstance(v, dict)}
    # Per-feed seen-store {url: [entry_key, ...]} for cross-RUN entry dedup: a
    # changed (200) feed's top-N overlaps day to day, so without this its
    # repeated entries would be re-captured into the append-only FTS5 store.
    seen_store = _fetch.load_json_store(seen_path)
    results = _fetch.fetch_all(feeds, top_n=top_n, cache=cache)

    out = AccumulateResult()
    for feed, payload in results:
        if isinstance(payload, _fetch.NotModified):
            out.unchanged += 1
            continue
        if isinstance(payload, Exception):
            out.errored += 1
            continue
        out.changed += 1
        url = feed.get("url")
        feed_seen = set(seen_store.get(url) or [])

        feed_failed = 0
        newly_captured: list[str] = []
        for entry in payload:
            key = _dedup.entry_key(entry)
            # An empty key (no link, no title) has no stable identity -> always
            # treated as new (cannot be deduped). Otherwise skip if already seen.
            if key and key in feed_seen:
                out.skipped_duplicate += 1
                continue
            res = _capture.capture_entry(entry, dry_run=dry_run)
            if res.status == "ok":
                out.captured += 1
                if key:
                    newly_captured.append(key)
            elif res.status == "dry-run":
                pass  # nothing written -> neither captured nor failed nor seen
            else:
                out.capture_failed += 1
                feed_failed += 1

        if feed_failed:
            # Roll this feed's validator back so it is re-fetched next run; the
            # uncaptured entries must not be hidden behind a future 304.
            if url in prior:
                cache[url] = prior[url]
            else:
                cache.pop(url, None)

        if newly_captured:
            # Append only successfully-captured keys (a failed capture stays
            # unseen so it is retried), then bound the per-feed list.
            combined = list(seen_store.get(url) or []) + newly_captured
            seen_store[url] = combined[-MAX_SEEN_PER_FEED:]

    # Persist refreshed validators + seen-store so the next run can ask "changed
    # since last?" and "captured already?". A dry run writes nothing to FTS5, so
    # it must NOT persist either (a later real run would otherwise 304-skip or
    # dedup-skip feeds/entries it never actually captured).
    if not dry_run:
        _fetch.save_feed_cache(cache_path, cache)
        _fetch.save_json_store(seen_path, seen_store)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="accumulate fresh feed entries into FTS5 (conditional GET)"
    )
    ap.add_argument("--feeds", type=Path, default=DEFAULT_FEEDS)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE, dest="cache_path")
    ap.add_argument("--seen", type=Path, default=None, dest="seen_path",
                    help="per-feed dedup seen-store (default: next to --cache)")
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--strict", action="store_true",
                    help="skip feeds flagged optional=true in feeds.toml")
    ap.add_argument("--dry-run", action="store_true",
                    help="build capture commands without writing to FTS5")
    args = ap.parse_args(argv)

    res = run(
        feeds_toml=args.feeds,
        cache_path=args.cache_path,
        seen_path=args.seen_path,
        top_n=args.top_n,
        strict=args.strict,
        dry_run=args.dry_run,
    )
    print(
        f"accumulate: {res.changed} changed, {res.unchanged} unchanged, "
        f"{res.errored} error feeds; captured {res.captured} entries"
        + (f", skipped {res.skipped_duplicate} duplicates" if res.skipped_duplicate else "")
        + (f" ({res.capture_failed} capture failures)" if res.capture_failed else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
