"""CLI: full-text search the local knowledge store.

  python -m phantom_ai_feed.recall "RAG latest"
  python -m phantom_ai_feed.recall "agent MCP" --limit 5
  python -m phantom_ai_feed.recall "vLLM" --db /path/to/aifeed.db
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import store as _store


def _utf8_stdout() -> None:
    """Feed titles carry emoji/CJK; a Windows console defaults to a legacy
    codepage (cp950/cp1252) that can't encode them and would crash on print.
    Make stdout UTF-8 and replace anything unencodable."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # already wrapped / not reconfigurable
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="full-text search the local phantom-ai-feed knowledge store"
    )
    ap.add_argument("query", help="FTS5 search query (e.g. 'agent MCP')")
    ap.add_argument("--db", type=Path, default=_store.DEFAULT_DB, dest="db_path")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args(argv)

    _utf8_stdout()
    rows = _store.recall(args.query, db_path=args.db_path, limit=args.limit)
    if not rows:
        print(f"recall: no matches for {args.query!r}", file=sys.stderr)
        return 1
    for r in rows:
        title = r["title"] or "(untitled)"
        print(f"- {title}  [{r['source']} · {r['category']} · {r['captured_at']}]")
        if r["link"]:
            print(f"  {r['link']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
