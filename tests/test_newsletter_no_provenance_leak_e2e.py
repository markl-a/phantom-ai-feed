"""Gap 3 follow-up — the weekly 'Ranked sources' provenance must NOT leak into
the reader-facing newsletter draft.

weekly.py now surfaces a "## 來源信度 / Ranked sources" block (credibility scores
+ cross-source corroboration counts) in the weekly digest — that is correct and
desired for the digest. But newsletter.py consumes the real weekly-<date>.md and
explicitly promises to "strip internal provenance lines that shouldn't face
readers". Raw credibility scores are exactly such internal provenance.

This drives the REAL chain end to end: produce an actual weekly digest from
file:// feeds (so the Ranked-sources block carries real scores), then assemble
the newsletter draft from it, and assert the digest keeps the provenance while
the reader-facing draft drops it.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import newsletter as _nl  # noqa: E402
from phantom_ai_feed import weekly as _weekly  # noqa: E402

SHARED_LINK = "https://example.com/leak-shared"


def _rss(pairs):
    items = "".join(
        f"<item><title>{t}</title><link>{l}</link>"
        f"<description>{t} — details.</description></item>"
        for t, l in pairs
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<rss version='2.0'><channel><title>c</title>{items}</channel></rss>"
    )


def _write_feeds(tmp_path: Path) -> Path:
    (tmp_path / "r.xml").write_text(
        _rss([("Leak Shared Story", SHARED_LINK),
              ("Leak Solo Story", "https://example.com/leak-solo")]),
        encoding="utf-8",
    )
    (tmp_path / "c.xml").write_text(
        _rss([("Leak Shared Story", SHARED_LINK)]), encoding="utf-8"
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


def test_ranked_sources_provenance_not_in_newsletter(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    toml = _write_feeds(tmp_path)
    today = _dt.date.today()

    weekly_path = _weekly.run(
        feeds_toml=toml, out_dir=log_dir, use_stub=True, force=True
    )
    weekly_md = weekly_path.read_text(encoding="utf-8")
    # The digest itself DOES surface the provenance (gap-3 behavior preserved).
    assert "Ranked sources" in weekly_md
    assert "credibility" in weekly_md.lower()
    assert "corroborated by" in weekly_md

    draft_path = _nl.run(log_dir=log_dir, end=today, force=True)
    draft = draft_path.read_text(encoding="utf-8")

    # The stories still reach the reader.
    assert "Leak Shared Story" in draft
    # ...but the internal scoring provenance does NOT.
    assert "Ranked sources" not in draft
    assert "credibility" not in draft.lower()
    assert "corroborated by" not in draft
