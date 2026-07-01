"""recall() snippet field — FTS5 snippet() on the MATCH path, empty on LIKE fallback."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import store  # noqa: E402


def test_recall_snippet_highlights_matched_token(tmp_path):
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
    assert "**transformer**" in rows[0]["snippet"]
    # existing keys/behavior unchanged
    assert rows[0]["title"] == "Sparse attention transformer"
    assert rows[0]["link"] == "http://e/a"
    assert rows[0]["source"] == "arxiv"


def test_recall_snippet_empty_on_like_fallback(tmp_path):
    db = tmp_path / "k.db"
    store.capture(
        {"title": "量子位:大模型推理加速新方法", "summary": "vLLM PagedAttention",
         "link": "l", "source": "zh-qbitai", "category": "zh"},
        db_path=db,
    )
    rows = store.recall("量子", db_path=db)  # falls back to LIKE (CJK tokenizer)
    assert rows
    assert rows[0]["snippet"] == ""


def test_recall_no_match_returns_empty_no_snippet_key_error(tmp_path):
    db = tmp_path / "k.db"
    store.capture({"title": "foo", "link": "http://e/f", "source": "s"}, db_path=db)
    assert store.recall("nonexistenttoken", db_path=db) == []
