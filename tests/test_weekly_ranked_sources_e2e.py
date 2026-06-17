"""Gap 3 — the WEEKLY digest must SURFACE its credibility/corroboration.

``weekly._collect_items`` already dedups and credibility-ranks the week's
entries (carrying each survivor's ``credibility`` score and cross-source
``cluster_sources``), but ``weekly.run`` wrote only the LLM/stub body — the
ranking was invisible in the produced file. The vision: "surfaces a ranked
digest through the PRODUCTION CLI path (not just unit-tested internals)".

This proves the surfacing END-TO-END through ``python -m phantom_ai_feed.weekly
--use-stub``: two ``file://`` feeds (research + community) share one story; the
written weekly digest must carry a "Ranked sources" provenance block listing the
credibility score and the cross-source corroboration count.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SHARED_LINK = "https://example.com/weekly-shared"


def _rss(pairs):
    items = "".join(
        f"<item><title>{t}</title><link>{l}</link>"
        f"<description>{t} — concrete details and numbers.</description></item>"
        for t, l in pairs
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<rss version='2.0'><channel><title>c</title>{items}</channel></rss>"
    )


def _write_feeds(tmp_path: Path) -> Path:
    (tmp_path / "r.xml").write_text(
        _rss([("Shared Weekly Story", SHARED_LINK),
              ("Solo Research Item", "https://example.com/solo")]),
        encoding="utf-8",
    )
    (tmp_path / "c.xml").write_text(
        _rss([("Shared Weekly Story", SHARED_LINK)]), encoding="utf-8"
    )
    toml = tmp_path / "feeds.toml"
    toml.write_text(
        "[[feed]]\n"
        'name = "arxiv-feed"\n'
        f'url = "{(tmp_path / "r.xml").as_uri()}"\n'
        'category = "research"\n\n'
        "[[feed]]\n"
        'name = "hn-feed"\n'
        f'url = "{(tmp_path / "c.xml").as_uri()}"\n'
        'category = "community"\n',
        encoding="utf-8",
    )
    return toml


def test_weekly_cli_surfaces_ranked_sources(tmp_path):
    toml = _write_feeds(tmp_path)
    out_dir = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "phantom_ai_feed.weekly",
         "--feeds", str(toml), "--out", str(out_dir),
         "--use-stub", "--force"],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    md = list(out_dir.glob("weekly-*.md"))
    assert md, f"no weekly digest written; stderr={proc.stderr}"
    body = md[0].read_text(encoding="utf-8")

    # A provenance block that surfaces the ranking.
    assert "Ranked sources" in body
    # The corroborated story's cross-source count is shown.
    assert "2 sources" in body
    assert "arxiv-feed" in body and "hn-feed" in body
    # A real credibility score (a number) is surfaced, not just an order.
    assert re.search(r"cred(?:ibility)?[^\n]*\d", body.lower())
    # The shared story is ranked above the solo one in that block.
    section = re.search(r"(?ms)^##[^\n]*Ranked sources.*\Z", body).group(0)
    assert section.index("Shared Weekly Story") < section.index("Solo Research Item")
