"""Structured knowledge-base data layer for captured feed items.

This module sits beside the existing FTS5 capture/recall store. ``KnowledgeBase``
keeps a small structured JSON sidecar under the same data directory while
delegating capture to the real local store path in ``capture.py``/``store.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import capture as _capture
from . import store as _store

DEFAULT_STORE = _store.DEFAULT_DB.parent / "knowledge_base.json"


class KnowledgeBase:
    """Persist structured topic summaries for captured feed items."""

    def __init__(
        self,
        store_path: str | Path = DEFAULT_STORE,
        *,
        db_path: str | Path = _store.DEFAULT_DB,
    ) -> None:
        self.store_path = Path(store_path)
        self.db_path = Path(db_path)

    def ingest(self, item: dict[str, Any]) -> dict[str, str]:
        """Capture ``item`` and persist one structured entry.

        Dedup is intentionally bounded: an existing entry with the same
        normalized ``source`` and ``topic`` is returned instead of creating a
        duplicate.
        """
        entry = _entry_from_item(item)
        entries = self._load_entries()
        for existing in entries:
            if _dedup_key(existing) == _dedup_key(entry):
                return existing

        result = _capture.capture_entry(item, db_path=self.db_path)
        if not result.ok:
            raise RuntimeError(result.detail or f"capture failed: {result.status}")

        entries.append(entry)
        self._write_entries(entries)
        return entry

    def query(self, topic: str) -> list[dict[str, str]]:
        """Return structured entries whose topic contains ``topic``."""
        q = (topic or "").strip().casefold()
        if not q:
            return []
        return [
            entry
            for entry in self._load_entries()
            if q in entry.get("topic", "").casefold()
        ]

    def list_entries(self) -> list[dict[str, str]]:
        """Return all structured entries in insertion order."""
        return self._load_entries()

    def _load_entries(self) -> list[dict[str, str]]:
        if not self.store_path.exists():
            return []
        raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise RuntimeError("knowledge base store must contain a JSON list")
        entries: list[dict[str, str]] = []
        for row in raw:
            if isinstance(row, dict):
                entries.append(
                    {
                        "topic": str(row.get("topic", "")),
                        "summary": str(row.get("summary", "")),
                        "source": str(row.get("source", "")),
                    }
                )
        return entries

    def _write_entries(self, entries: list[dict[str, str]]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _entry_from_item(item: dict[str, Any]) -> dict[str, str]:
    topic = _first_text(item, "topic", "title")
    summary = _first_text(item, "summary", "summary_excerpt")
    source = _first_text(item, "source") or "phantom-ai-feed"
    return {"topic": topic, "summary": summary, "source": source}


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _dedup_key(entry: dict[str, str]) -> tuple[str, str]:
    return (
        entry.get("source", "").strip().casefold(),
        entry.get("topic", "").strip().casefold(),
    )


__all__ = ["DEFAULT_STORE", "KnowledgeBase"]
