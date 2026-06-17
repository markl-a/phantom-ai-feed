"""Gap 2 — the DAILY digest must dedup + credibility-rank across sources.

The final-form vision says the digest "ranks items by source credibility,
de-duplicates/corroborates across sources". But ``digest.py`` imported neither
``dedup`` nor ``credibility`` — those modules were fully unit-tested yet
unreachable from the production daily CLI. A story appearing on both arXiv and
Hacker News was listed twice, unranked.

This proves the wiring END-TO-END through ``python -m phantom_ai_feed.digest``:
two ``file://`` feeds (a research feed and a community feed) carry the SAME
story plus a unique one; the CLI must emit a "Top picks" section that lists the
shared story ONCE, credibility-ranked, annotated with its cross-source
corroboration count.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SHARED_LINK = "https://example.com/shared-breakthrough"


def _rss(title_link_pairs):
    items = "".join(
        f"<item><title>{t}</title><link>{l}</link>"
        f"<description>{t} details.</description></item>"
        for t, l in title_link_pairs
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<rss version='2.0'><channel><title>c</title>{items}</channel></rss>"
    )


def _write_feeds(tmp_path: Path) -> Path:
    research = tmp_path / "research.xml"
    research.write_text(
        _rss([("Shared Breakthrough Model", SHARED_LINK),
              ("Niche research note", "https://example.com/niche")]),
        encoding="utf-8",
    )
    community = tmp_path / "community.xml"
    community.write_text(
        _rss([("Shared Breakthrough Model", SHARED_LINK)]),
        encoding="utf-8",
    )
    toml = tmp_path / "feeds.toml"
    toml.write_text(
        "[[feed]]\n"
        'name = "arxiv-feed"\n'
        f'url = "{research.as_uri()}"\n'
        'category = "research"\n\n'
        "[[feed]]\n"
        'name = "hn-feed"\n'
        f'url = "{community.as_uri()}"\n'
        'category = "community"\n',
        encoding="utf-8",
    )
    return toml


def _run_digest(tmp_path: Path) -> str:
    toml = _write_feeds(tmp_path)
    out_dir = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "phantom_ai_feed.digest",
         "--feeds", str(toml), "--out", str(out_dir),
         "--use-stub", "--force"],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    md = list(out_dir.glob("20*.md"))
    assert md, f"no digest written; stderr={proc.stderr}"
    return md[0].read_text(encoding="utf-8")


def _top_picks_section(body: str) -> str:
    # Everything from the Top picks heading up to the next '## ' feed section.
    m = re.search(r"(?ms)^##[^\n]*Top picks.*?(?=^##\s|\Z)", body)
    assert m, f"no Top picks section in digest:\n{body}"
    return m.group(0)


def test_daily_digest_has_credibility_ranked_deduped_top_picks(tmp_path):
    body = _run_digest(tmp_path)
    section = _top_picks_section(body)

    # The shared story is corroborated across the two distinct sources.
    assert "2 sources" in section
    assert "arxiv-feed" in section and "hn-feed" in section

    # It is listed ONCE in Top picks (deduped), not twice — count the link
    # form (the title also recurs inside its own summary line).
    assert section.count("[Shared Breakthrough Model]") == 1

    # Credibility-ranked: the corroborated research story outranks the
    # single-source niche note (appears earlier in the ranked list).
    i_shared = section.index("Shared Breakthrough Model")
    i_niche = section.index("Niche research note")
    assert i_shared < i_niche, "expected corroborated story ranked first"

    # A credibility score is surfaced (not just an opaque order).
    assert re.search(r"cred(?:ibility)?[^\n]*\d", section.lower())
