"""Weekly AI-news digest: fetch → ONE LLM analysis pass → ranked markdown.

Unlike `digest.py` (which summarises each entry of a single day), this
gathers a wider slice of every feed and makes a *single* `phantom exec`
call to rank and analyse the week's most important AI developments.

Pipeline:
  load feeds.toml → fetch_all (higher top_n) → concat titles+excerpts
  → one phantom-exec analysis → write
  ~/.phantom-mesh/logs/phantom-ai-feed/weekly-<date>.md

CLI:
  python -m phantom_ai_feed.weekly                 # real LLM via `phantom exec`
  python -m phantom_ai_feed.weekly --use-stub      # no API call (extractive)
  python -m phantom_ai_feed.weekly --top-n 8       # widen per-feed window
  python -m phantom_ai_feed.weekly --out /tmp/foo  # override out dir
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path

from . import credibility as _cred
from . import dedup as _dedup
from . import fetch as _fetch
from . import summarize as _sum

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEEDS = REPO_ROOT / "sources" / "feeds.toml"
DEFAULT_OUT = Path.home() / ".phantom-mesh" / "logs" / "phantom-ai-feed"
DEFAULT_TOP_N = 6
# Cap the blob we hand the model so a single exec stays bounded.
MAX_BLOB_CHARS = 16000

# Sentinel comment markers wrapping the internal ranking provenance block. The
# weekly digest is meant to SHOW this (credibility scores / corroboration), but
# downstream reader-facing consumers (newsletter.py) strip anything between
# these markers so raw internal scoring never faces subscribers.
PROVENANCE_START = "<!-- phantom-ai-feed:provenance:start -->"
PROVENANCE_END = "<!-- phantom-ai-feed:provenance:end -->"


def _collect_items(
    feeds_toml: Path, top_n: int, *, dedup: bool = True, rank: bool = True,
    strict: bool = False,
) -> tuple[list[dict], int, int]:
    """Fetch every feed; return (entries, ok_feed_count, total_feed_count).

    When ``dedup`` is True (default) the entries are collapsed across sources
    via ``dedup.cluster_entries`` so a story that appears on arXiv, Reddit, and
    HN is ranked once. Each cluster's representative is then chosen by
    ``credibility.pick_representative`` — the MOST-credible member wins, so a
    research-feed version of a story beats an earlier-seen HN version rather
    than keeping the first-seen entry. The surviving representative carries its
    ``cluster_size`` / ``cluster_sources`` for downstream credibility weighting.

    When ``rank`` is True (default) the (deduped) entries are then ordered
    most-credible-first via ``credibility.rank_entries``, biased by per-category
    trust, this run's fetch-success history, and cross-source corroboration, so
    the most trustworthy/corroborated stories lead the blob handed to the LLM.
    """
    feeds = _fetch.filter_feeds(_fetch.load_feeds(feeds_toml), strict=strict)
    if not feeds:
        raise SystemExit(f"no [[feed]] entries in {feeds_toml}")
    raw = _fetch.fetch_all(feeds, top_n=top_n)
    history = _cred.build_fetch_history(raw)
    entries: list[dict] = []
    ok = 0
    for _feed, payload in raw:
        if isinstance(payload, Exception):
            continue
        ok += 1
        entries.extend(payload)
    if dedup:
        # Cluster cross-source duplicates, then let credibility pick each
        # cluster's representative — the MOST-credible member (e.g. a research
        # feed) wins over an earlier-seen but lower-trust source (e.g. HN),
        # instead of blindly keeping the first-seen entry. The cluster-level
        # annotations (cluster_size / cluster_sources) are carried onto the
        # representative for downstream corroboration weighting.
        representatives: list[dict] = []
        for cluster in _dedup.cluster_entries(entries):
            rep = dict(cluster.representative)
            rep["cluster_size"] = cluster.size
            rep["cluster_sources"] = cluster.sources
            representatives.append(
                _cred.pick_representative(rep, cluster.entries, history=history)
            )
        entries = representatives
    if rank:
        entries = _cred.rank_entries(entries, history=history)
    return entries, ok, len(feeds)


def _render_ranked_sources(entries: list[dict]) -> str:
    """Surface the credibility ranking + cross-source corroboration.

    ``_collect_items`` already deduped and credibility-ranked the entries (each
    carries its ``credibility`` score and the distinct ``cluster_sources`` that
    corroborated it), but that work was previously invisible in the written
    digest. This renders a provenance block so the production CLI output — not
    just the unit tests — shows WHY each story was ranked where it was.
    """
    lines = [
        PROVENANCE_START,
        "## 來源信度 / Ranked sources",
        "",
        "_依可信度排序(類別信度 + 抓取成功率 + 跨來源佐證);"
        "已跨來源去重。Credibility-ranked, cross-source deduped._",
        "",
    ]
    for i, e in enumerate(entries, 1):
        title = (e.get("title") or "(untitled)").strip()
        cred = e.get("credibility", 0.0)
        sources = e.get("cluster_sources") or (
            [e["source"]] if e.get("source") else []
        )
        n = len(sources) or int(e.get("cluster_size", 1) or 1)
        corro = f"{n} source{'s' if n != 1 else ''}"
        if sources:
            corro += ": " + ", ".join(sources)
        lines.append(
            f"{i}. **{title}** — credibility {cred} · corroborated by {corro}"
        )
    lines.append(PROVENANCE_END)
    lines.append("")
    return "\n".join(lines)


def _build_blob(entries: list[dict]) -> str:
    lines: list[str] = []
    for e in entries:
        title = (e.get("title") or "(untitled)").strip()
        src = (e.get("source") or "").strip()
        excerpt = " ".join((e.get("summary_excerpt") or "").split())
        head = f"- [{src}] {title}" if src else f"- {title}"
        lines.append(head)
        if excerpt:
            lines.append(f"  {excerpt}")
    return "\n".join(lines)[:MAX_BLOB_CHARS]


def _build_weekly_prompt(blob: str) -> str:
    return (
        "You are an AI engineering news editor writing a WEEKLY digest for a "
        "Chinese-speaking senior ML/AI engineer. From the raw feed items below "
        "(one week's worth, across arXiv, blogs, and Hacker News), do the "
        "following:\n"
        "1. Pick the TOP 5-7 most important developments. Rank them.\n"
        "2. For each, give a one-line title and 1-2 sentences on WHY it matters "
        "(novel idea / concrete numbers / who should care).\n"
        "3. End with a 2-3 sentence overall TREND commentary for the week.\n"
        "Write in 繁體中文 mixed with key English technical terms. Use Markdown "
        "(numbered list for the ranked items, a '## 本週趨勢' heading for the "
        "commentary). Output the digest body only, no preamble.\n\n"
        "=== RAW FEED ITEMS ===\n" + blob
    )


def _analyze(blob: str, *, use_stub: bool) -> tuple[str, str]:
    """Return (body, provider_badge). One LLM call via phantom exec (reused)."""
    prompt = _build_weekly_prompt(blob)
    if use_stub or not shutil.which("phantom"):
        return _sum.summarize_stub(blob, max_words=400), "stub-extractive"
    try:
        # prompt is already fully formed — do NOT re-wrap with the daily preamble.
        body = _sum.summarize_phantom(prompt, max_words=700, timeout_s=180, wrap=False)
        return body, "phantom-exec"
    except (OSError, RuntimeError) as e:
        # Honest degradation: never silently fake LLM output.
        return (
            _sum.summarize_stub(blob, max_words=400)
            + f"\n\n_(phantom exec failed: {e}; extractive fallback used)_",
            "stub-extractive",
        )


def run(
    feeds_toml: Path = DEFAULT_FEEDS,
    out_dir: Path = DEFAULT_OUT,
    *,
    use_stub: bool = False,
    top_n: int = DEFAULT_TOP_N,
    force: bool = False,
    strict: bool = False,
) -> Path:
    today = _dt.date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"weekly-{today.isoformat()}.md"
    if out_path.exists() and not force:
        print(f"already wrote {out_path} — skipping (idempotent)")
        return out_path

    entries, ok, total = _collect_items(feeds_toml, top_n, strict=strict)
    if not entries:
        raise SystemExit("no entries fetched from any feed — aborting")

    body, badge = _analyze(_build_blob(entries), use_stub=use_stub)
    header = (
        f"# phantom-ai-feed weekly digest — week ending {today.isoformat()}\n\n"
        f"_Generated by phantom_ai_feed.weekly ({badge}); "
        f"{len(entries)} items from {ok}/{total} feeds._\n\n"
    )
    ranked = _render_ranked_sources(entries)
    out_path.write_text(
        header + body + "\n\n" + ranked + "\n", encoding="utf-8"
    )
    print(f"wrote {out_path} ({len(entries)} items, {ok}/{total} feeds OK, {badge})")
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="phantom-ai-feed weekly digest")
    ap.add_argument("--feeds", type=Path, default=DEFAULT_FEEDS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--use-stub", action="store_true",
                    help="skip phantom exec, use stdlib extractive summary")
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N,
                    help="entries fetched per feed (wider than daily)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite this week's digest if present")
    ap.add_argument("--strict", action="store_true",
                    help="skip feeds flagged optional=true in feeds.toml")
    args = ap.parse_args(argv)
    run(
        feeds_toml=args.feeds,
        out_dir=args.out,
        use_stub=args.use_stub,
        top_n=args.top_n,
        force=args.force,
        strict=args.strict,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
