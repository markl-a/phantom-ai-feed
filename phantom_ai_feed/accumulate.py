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
from . import fetch as _fetch

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS = REPO_ROOT / "sources" / "feeds.toml"
DEFAULT_CACHE = (
    Path.home() / ".phantom-mesh" / "logs" / "phantom-ai-feed" / "fetch-cache.json"
)


@dataclass
class AccumulateResult:
    """Per-run tally.

    - ``changed``        feeds that returned new content (HTTP 200)
    - ``unchanged``      feeds skipped via HTTP 304 (NotModified)
    - ``errored``        feeds whose fetch failed
    - ``captured``       entries successfully written into FTS5
    - ``capture_failed`` entries whose capture failed (e.g. no phantom CLI)
    """

    changed: int = 0
    unchanged: int = 0
    errored: int = 0
    captured: int = 0
    capture_failed: int = 0

    @property
    def total_feeds(self) -> int:
        return self.changed + self.unchanged + self.errored


def _for_capture(entry: dict) -> dict:
    """Shape a raw fetched entry for the capture seam.

    Fetched entries carry ``summary_excerpt``; ``capture._fold_text`` reads
    ``summary``. Copy the excerpt across (no LLM) so FTS5 can search the body
    text, not just the title. Leaves an existing ``summary`` untouched.
    """
    if not entry.get("summary"):
        entry = {**entry, "summary": entry.get("summary_excerpt", "")}
    return entry


def run(
    feeds_toml: Path = DEFAULT_FEEDS,
    *,
    cache_path: Path = DEFAULT_CACHE,
    top_n: int = 3,
    strict: bool = False,
    dry_run: bool = False,
) -> AccumulateResult:
    feeds = _fetch.filter_feeds(_fetch.load_feeds(feeds_toml), strict=strict)
    if not feeds:
        raise SystemExit(f"no [[feed]] entries in {feeds_toml}")

    cache = _fetch.load_feed_cache(cache_path)
    results = _fetch.fetch_all(feeds, top_n=top_n, cache=cache)

    out = AccumulateResult()
    for _feed, payload in results:
        if isinstance(payload, _fetch.NotModified):
            out.unchanged += 1
            continue
        if isinstance(payload, Exception):
            out.errored += 1
            continue
        out.changed += 1
        for entry in payload:
            res = _capture.capture_entry(_for_capture(entry), dry_run=dry_run)
            if res.ok:
                out.captured += 1
            else:
                out.capture_failed += 1

    # Persist refreshed validators so the next run can ask "changed since last?".
    _fetch.save_feed_cache(cache_path, cache)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="accumulate fresh feed entries into FTS5 (conditional GET)"
    )
    ap.add_argument("--feeds", type=Path, default=DEFAULT_FEEDS)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE, dest="cache_path")
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--strict", action="store_true",
                    help="skip feeds flagged optional=true in feeds.toml")
    ap.add_argument("--dry-run", action="store_true",
                    help="build capture commands without writing to FTS5")
    args = ap.parse_args(argv)

    res = run(
        feeds_toml=args.feeds,
        cache_path=args.cache_path,
        top_n=args.top_n,
        strict=args.strict,
        dry_run=args.dry_run,
    )
    print(
        f"accumulate: {res.changed} changed, {res.unchanged} unchanged, "
        f"{res.errored} error feeds; captured {res.captured} entries"
        + (f" ({res.capture_failed} capture failures)" if res.capture_failed else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
