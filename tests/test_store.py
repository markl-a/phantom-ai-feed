"""Local SQLite FTS5 knowledge store — capture + full-text recall, no daemon."""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import store  # noqa: E402


def test_capture_then_recall(tmp_path):
    db = tmp_path / "k.db"
    store.capture(
        {
            "title": "Sparse attention transformer",
            "summary": "38% less KV-cache on a 70B model",
            "link": "http://e/a",
            "source": "arxiv",
            "category": "research",
        },
        db_path=db,
    )
    rows = store.recall("transformer", db_path=db)
    assert len(rows) == 1
    assert rows[0]["title"] == "Sparse attention transformer"
    assert rows[0]["link"] == "http://e/a"
    assert rows[0]["source"] == "arxiv"


def test_recall_matches_summary_body(tmp_path):
    db = tmp_path / "k.db"
    store.capture({"title": "t", "summary": "paged attention serving", "link": "l", "source": "s"}, db_path=db)
    assert store.recall("paged", db_path=db)


def test_capture_falls_back_to_excerpt(tmp_path):
    db = tmp_path / "k.db"
    store.capture({"title": "t", "summary_excerpt": "novel quantization trick", "link": "l", "source": "s"}, db_path=db)
    assert store.recall("quantization", db_path=db)


def test_recall_no_match_returns_empty(tmp_path):
    db = tmp_path / "k.db"
    store.capture({"title": "foo", "link": "http://e/f", "source": "s"}, db_path=db)
    assert store.recall("nonexistenttoken", db_path=db) == []


def test_recall_respects_limit(tmp_path):
    db = tmp_path / "k.db"
    for i in range(5):
        store.capture({"title": f"model {i} attention", "link": f"l{i}", "source": "s"}, db_path=db)
    assert len(store.recall("attention", db_path=db, limit=3)) == 3


def test_recall_missing_db_returns_empty(tmp_path):
    assert store.recall("anything", db_path=tmp_path / "absent.db") == []


def test_recall_tolerates_fts5_special_chars(tmp_path):
    """A user query with FTS5 operator chars must not raise — return [] instead."""
    db = tmp_path / "k.db"
    store.capture({"title": "hello", "link": "l", "source": "s"}, db_path=db)
    assert store.recall('"(', db_path=db) == []


def test_captured_at_recorded(tmp_path):
    db = tmp_path / "k.db"
    store.capture({"title": "dated", "link": "l", "source": "s"}, db_path=db, on=_dt.date(2026, 6, 21))
    rows = store.recall("dated", db_path=db)
    assert rows[0]["captured_at"] == "2026-06-21"
