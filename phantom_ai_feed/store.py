"""Local SQLite FTS5 knowledge store — pure stdlib, no daemon.

A local-first capture sink for ``accumulate``, decoupled from the phantom mesh
daemon: each captured entry becomes a row in an FTS5 virtual table, so the
knowledge base is full-text searchable via ``recall`` without ``phantom serve``
running. The DB lives at ``~/.phantom-mesh/logs/phantom-ai-feed/aifeed.db``.

This is the Phase-2 "FTS5 capture as a first-class citizen" path. The phantom
CLI seam in ``capture.py`` remains available as an opt-in backend for when the
mesh daemon is wired back in.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
from pathlib import Path

DEFAULT_DB = (
    Path.home() / ".phantom-mesh" / "logs" / "phantom-ai-feed" / "aifeed.db"
)

# Stored columns. ``captured_at`` is UNINDEXED (kept for display/ordering, not
# searched); the text columns are full-text indexed.
_COLUMNS = ("title", "summary", "link", "source", "category", "captured_at")
_CREATE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS entries USING fts5("
    "title, summary, link, source, category, captured_at UNINDEXED)"
)


def _connect(db_path: Path | str) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.execute(_CREATE)
    return con


def capture(entry: dict, *, db_path: Path | str = DEFAULT_DB, on: _dt.date | None = None) -> bool:
    """Insert one entry as a row in the FTS5 store. Returns True on success.

    ``summary`` falls back to ``summary_excerpt`` (raw fetched entries carry the
    excerpt, the digest path carries an LLM summary) so the body is always
    indexed. Raises on a genuine DB/disk error (the caller decides how to react).
    """
    summary = (entry.get("summary") or entry.get("summary_excerpt") or "").strip()
    row = (
        (entry.get("title") or "").strip(),
        summary,
        (entry.get("link") or "").strip(),
        (entry.get("source") or "phantom-ai-feed").strip() or "phantom-ai-feed",
        (entry.get("category") or "misc").strip() or "misc",
        (on or _dt.date.today()).isoformat(),
    )
    con = _connect(db_path)
    try:
        with con:
            con.execute(
                "INSERT INTO entries "
                "(title, summary, link, source, category, captured_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                row,
            )
    finally:
        con.close()
    return True


def recall(query: str, *, db_path: Path | str = DEFAULT_DB, limit: int = 10) -> list[dict]:
    """Full-text search the store, most-relevant first. Returns a list of dicts.

    A missing DB or an unparseable FTS5 query (user typed bare operator chars)
    returns ``[]`` rather than raising — recall is best-effort."""
    p = Path(db_path)
    if not p.exists():
        return []
    con = _connect(db_path)
    try:
        try:
            cur = con.execute(
                "SELECT title, summary, link, source, category, captured_at "
                "FROM entries WHERE entries MATCH ? ORDER BY rank LIMIT ?",
                (query, limit),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        con.close()
    return [dict(zip(_COLUMNS, r)) for r in rows]
