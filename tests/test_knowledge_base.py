from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed.knowledge_base import KnowledgeBase  # noqa: E402


def test_ingest_persists_and_reloads(tmp_path: Path) -> None:
    store_path = tmp_path / "knowledge_base.json"
    db_path = tmp_path / "aifeed.db"
    kb = KnowledgeBase(store_path=store_path, db_path=db_path)

    entry = kb.ingest(
        {
            "title": "Sparse attention transformer",
            "summary": "38% less KV-cache on a 70B model",
            "link": "http://e/a",
            "source": "arxiv",
        }
    )

    assert entry == {
        "topic": "Sparse attention transformer",
        "summary": "38% less KV-cache on a 70B model",
        "source": "arxiv",
    }
    assert KnowledgeBase(store_path=store_path, db_path=db_path).list_entries() == [entry]


def test_ingest_dedups_same_source_and_topic(tmp_path: Path) -> None:
    kb = KnowledgeBase(
        store_path=tmp_path / "knowledge_base.json",
        db_path=tmp_path / "aifeed.db",
    )
    item = {
        "title": "RAG evaluation harness",
        "summary": "local recall regression checks",
        "link": "http://e/rag",
        "source": "synthetic-research",
    }

    first = kb.ingest(item)
    second = kb.ingest({**item, "summary": "updated summary should not duplicate"})

    assert second == first
    assert kb.list_entries() == [first]


def test_query_returns_ingested_entry(tmp_path: Path) -> None:
    kb = KnowledgeBase(
        store_path=tmp_path / "knowledge_base.json",
        db_path=tmp_path / "aifeed.db",
    )
    entry = kb.ingest(
        {
            "title": "量子位: 大模型推理加速新方法",
            "summary_excerpt": "vLLM PagedAttention",
            "link": "http://e/qbit",
            "source": "zh-qbitai",
        }
    )

    assert kb.query("推理加速") == [entry]
