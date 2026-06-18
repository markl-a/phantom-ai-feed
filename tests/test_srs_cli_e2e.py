"""Gap — the SM-2 spaced-repetition loop must be REACHABLE from the real CLI.

The README advertises SM-2 spaced repetition, but the interview-question
generator was write-only: questions went to a ``.md`` and nothing captured
answers, grades, or due-dates. ``phantom_ai_feed/srs.py`` now closes that loop.

This test proves the loop END-TO-END through the production CLI
(``python -m phantom_ai_feed.srs``) — never an in-isolation call of the SM-2
function. It records answers via the REAL ``srs answer`` command and then asks
the REAL ``srs due`` command which cards fall due on specific dates, asserting
that SM-2's interval scheduling (1 day → 6 days, and the grade<3 reset) is
exactly what drives the due list.

A throwaway ``--store`` under ``tmp_path`` is used everywhere, so the real
``~/.phantom-mesh`` store is never touched.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _srs(store: Path, *args: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "phantom_ai_feed.srs", *args,
         "--store", str(store)],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, f"srs {args} failed: {proc.stderr}"
    return proc.stdout


def _due_ids(store: Path, on: str) -> list[str]:
    out = _srs(store, "due", "--on", on)
    ids = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("- "):
            ids.append(line[2:].split(" ", 1)[0])
    return ids


def test_srs_answer_then_due_drives_sm2_scheduling(tmp_path):
    store = tmp_path / "srs.jsonl"

    # ---- First answer: a confident grade 5 on a new card. -------------------
    # SM-2 for a brand-new card with grade>=3 gives interval = 1 day.
    out = _srs(store, "answer", "q1", "--grade", "5", "--on", "2026-01-01")
    assert "due=2026-01-02" in out, out
    assert "interval=1d" in out

    # The real CLI must persist to the store we pointed at — NOT the real one.
    assert store.exists()

    # Not due yet the same day (due_date 01-02 > 01-01).
    assert _due_ids(store, "2026-01-01") == []
    # Due exactly on its scheduled day.
    assert _due_ids(store, "2026-01-02") == ["q1"]

    # ---- Second answer: grade 5 again moves the interval 1 -> 6 (SM-2). -----
    out = _srs(store, "answer", "q1", "--grade", "5", "--on", "2026-01-02")
    assert "interval=6d" in out
    assert "due=2026-01-08" in out, out

    # The 6-day interval is what the REAL due command now schedules on:
    assert _due_ids(store, "2026-01-07") == []          # not yet
    assert _due_ids(store, "2026-01-08") == ["q1"]      # exactly 6 days later

    # ---- A failed card (grade<3) must RESET to a 1-day interval. ------------
    out = _srs(store, "answer", "q2", "--grade", "2", "--on", "2026-01-02")
    assert "interval=1d" in out
    assert "due=2026-01-03" in out, out

    # On 2026-01-03 only the reset card q2 is due (q1 sleeps until 01-08),
    # proving the due list is driven by per-card SM-2 state, sorted.
    assert _due_ids(store, "2026-01-03") == ["q2"]

    # On 2026-01-08 both are due, sorted by (due_date, question_id): q2's
    # earlier due date (01-03) sorts ahead of q1's (01-08).
    assert _due_ids(store, "2026-01-08") == ["q2", "q1"]

    # ---- The due command also writes a review file (printed path). ---------
    out = _srs(store, "due", "--on", "2026-01-08")
    wrote = [ln for ln in out.splitlines() if ln.startswith("wrote ")]
    assert wrote, out
    review = Path(wrote[0][len("wrote "):])
    assert review.exists()
    body = review.read_text(encoding="utf-8")
    assert "q1" in body and "q2" in body
    assert "2 cards" in body


def test_generated_questions_register_as_due_cards_through_cli(tmp_path):
    """The optional wiring: generating interview questions via the REAL
    interview-questions CLI with ``--register-srs`` seeds the SRS store, and the
    REAL ``srs due`` CLI then surfaces those brand-new cards as due immediately
    (interval 0). Proves the generator is no longer write-only / a dead loop."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    # A digest the stub generator can mine topic headings from.
    (log_dir / "2026-01-05.md").write_text(
        "# digest\n\n## Transformers\nfoo\n\n## RAG\nbar\n",
        encoding="utf-8",
    )
    store = tmp_path / "srs.jsonl"

    proc = subprocess.run(
        [sys.executable, "-m", "phantom_ai_feed.interview_questions",
         "--use-stub", "--end", "2026-01-10",
         "--log-dir", str(log_dir), "--register-srs", str(store)],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "registered" in proc.stdout, proc.stdout
    assert store.exists()

    # Brand-new cards are due on their registration date (interval 0).
    ids = _due_ids(store, "2026-01-10")
    assert ids, "no registered cards surfaced as due via the real srs CLI"
    assert all(qid.startswith("2026-01-10-q") for qid in ids), ids
