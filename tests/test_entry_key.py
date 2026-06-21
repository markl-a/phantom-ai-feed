"""dedup.entry_key — stable per-entry identity for cross-run dedup."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import dedup  # noqa: E402


def test_entry_key_uses_normalized_link():
    """Tracking params / www / scheme / trailing slash collapse to one key
    (reusing normalize_url) — the same article via two URLs is one entry."""
    a = {"link": "https://www.Example.com/post/?utm_source=x"}
    b = {"link": "http://example.com/post"}
    assert dedup.entry_key(a) == dedup.entry_key(b)
    assert dedup.entry_key(a)  # non-empty


def test_entry_key_link_beats_title():
    e = {"link": "https://e/x", "title": "whatever"}
    assert dedup.entry_key(e) == dedup.normalize_url("https://e/x")


def test_entry_key_falls_back_to_title_when_no_link():
    e = {"title": "PagedAttention speeds up LLM serving", "link": None}
    k = dedup.entry_key(e)
    assert k.startswith("t:")
    assert dedup.entry_key(dict(e)) == k  # deterministic


def test_entry_key_empty_when_no_link_no_title():
    assert dedup.entry_key({"link": "", "title": ""}) == ""
    assert dedup.entry_key({}) == ""


def test_entry_key_different_links_differ():
    assert dedup.entry_key({"link": "https://e/a"}) != dedup.entry_key(
        {"link": "https://e/b"}
    )


def test_entry_key_distinct_titles_do_not_collide():
    """The link-less fallback must be EXACT identity, not the fuzzy
    stopword-stripped clustering used for cross-source merge — otherwise two
    different stories whose content tokens coincide would be wrongly deduped
    (silently dropping a real entry)."""
    a = {"title": "A new X model", "link": None}
    b = {"title": "New model X released", "link": None}
    assert dedup.entry_key(a) != dedup.entry_key(b)
