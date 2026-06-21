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
# searched); the text columns are full-text indexed. The INSERT/SELECT SQL is
# DERIVED from this tuple so the three never drift (a mismatch would silently
# mislabel columns on read).
_COLUMNS = ("title", "summary", "link", "source", "category", "captured_at")
_CREATE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS entries USING fts5("
    "title, summary, link, source, category, captured_at UNINDEXED)"
)
_INSERT = (
    f"INSERT INTO entries ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _COLUMNS)})"
)
_SELECT = (
    f"SELECT {', '.join(_COLUMNS)} FROM entries "
    "WHERE entries MATCH ? ORDER BY rank LIMIT ?"
)


def _connect(db_path: Path | str) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # timeout= sets SQLite's busy-timeout so a concurrent writer (the scheduled
    # accumulate run) and reader (an interactive recall) wait briefly instead of
    # erroring with "database is locked"; WAL lets them proceed concurrently.
    con = sqlite3.connect(str(p), timeout=5.0)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_CREATE)
    except sqlite3.Error:
        con.close()  # don't leak the handle if schema setup fails
        raise
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
            con.execute(_INSERT, row)
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
    try:
        con = _connect(db_path)
    except sqlite3.Error:
        return []  # corrupt/locked DB — best-effort recall yields nothing
    try:
        try:
            rows = con.execute(_SELECT, (query, limit)).fetchall()
        except sqlite3.Error:
            # Unparseable FTS5 query, or a corrupt DB surfacing on read.
            return []
    finally:
        con.close()
    return [dict(zip(_COLUMNS, r)) for r in rows]
