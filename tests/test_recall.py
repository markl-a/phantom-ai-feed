"""recall CLI — search the local FTS5 store from the command line."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import recall, store  # noqa: E402


def test_recall_cli_prints_hit(tmp_path, capsys):
    db = tmp_path / "k.db"
    store.capture(
        {"title": "vLLM paged attention", "link": "http://e/v", "source": "blog", "category": "blog"},
        db_path=db,
    )
    rc = recall.main(["paged", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "vLLM paged attention" in out
    assert "http://e/v" in out


def test_recall_cli_prints_summary_body(tmp_path, capsys):
    db = tmp_path / "k.db"
    store.capture(
        {
            "title": "vLLM paged attention",
            "summary": "38% less KV-cache on a 70B model",
            "link": "http://e/v",
            "source": "blog",
            "category": "blog",
        },
        db_path=db,
    )
    recall.main(["paged", "--db", str(db)])
    out = capsys.readouterr().out
    assert "38% less KV-cache on a 70B model" in out


def test_recall_cli_truncates_long_summary(tmp_path, capsys):
    db = tmp_path / "k.db"
    long_summary = "x " * 200  # far past the CLI's one-line truncation limit
    store.capture(
        {"title": "t", "summary": long_summary, "link": "l", "source": "s"},
        db_path=db,
    )
    recall.main(["t", "--db", str(db)])
    out = capsys.readouterr().out
    assert long_summary.strip() not in out
    assert "…" in out


def test_recall_cli_no_match_returns_1(tmp_path, capsys):
    db = tmp_path / "k.db"
    store.capture({"title": "x", "link": "l", "source": "s"}, db_path=db)
    rc = recall.main(["nonexistenttoken", "--db", str(db)])
    assert rc == 1


def test_recall_cli_respects_limit(tmp_path, capsys):
    db = tmp_path / "k.db"
    for i in range(4):
        store.capture({"title": f"model {i} attention", "link": f"l{i}", "source": "s"}, db_path=db)
    recall.main(["attention", "--db", str(db), "--limit", "2"])
    out = capsys.readouterr().out
    assert out.count("attention") == 2
