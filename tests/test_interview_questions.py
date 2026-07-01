"""Hermetic unit tests for the two pure helpers in interview_questions.py:
``_extract_questions`` (parse numbered question lines) and
``_stub_questions`` (build the templated question bank from week topics).
Both are otherwise exercised only indirectly via ``run()``.
"""
from __future__ import annotations

import datetime as _dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import interview_questions as _iq  # noqa: E402


# --------------------------------------------------------------------------- #
# _extract_questions                                                          #
# --------------------------------------------------------------------------- #
def test_extract_questions_basic():
    body = "intro\n1. What is X?\n2. Explain Y.\n"
    end = _dt.date(2026, 6, 27)
    assert _iq._extract_questions(body, end) == [
        ("2026-06-27-q1", "What is X?"),
        ("2026-06-27-q2", "Explain Y."),
    ]


def test_extract_questions_ignores_non_numbered_lines():
    body = "Some text\n- bullet\n1. Only this one\nAnother line\n"
    result = _iq._extract_questions(body, _dt.date(2026, 1, 1))
    assert result == [("2026-01-01-q1", "Only this one")]


def test_extract_questions_strips_surrounding_whitespace():
    body = "1.   Question with leading spaces   \n"
    result = _iq._extract_questions(body, _dt.date(2026, 1, 1))
    assert result == [("2026-01-01-q1", "Question with leading spaces")]


def test_extract_questions_multi_digit_number():
    body = "10. Tenth question\n"
    result = _iq._extract_questions(body, _dt.date(2026, 1, 1))
    assert result == [("2026-01-01-q10", "Tenth question")]


def test_extract_questions_empty_body_returns_empty():
    assert _iq._extract_questions("", _dt.date(2026, 1, 1)) == []


def test_extract_questions_id_uses_end_date_not_body_content():
    body = "1. Q one\n"
    result = _iq._extract_questions(body, _dt.date(2025, 12, 31))
    assert result[0][0] == "2025-12-31-q1"


# --------------------------------------------------------------------------- #
# _stub_questions                                                             #
# --------------------------------------------------------------------------- #
def test_stub_questions_header_and_line_format():
    week = [(_dt.date(2026, 1, 1), "## Sparse Attention\nsome text")]
    result = _iq._stub_questions(week)
    lines = result.split("\n")
    assert lines[0] == "_Stub generator: questions templated from this week's top sources._"
    assert lines[1] == ""
    assert lines[2].startswith("1. ")


def test_stub_questions_uses_most_mentioned_heading_topic():
    week = [
        (_dt.date(2026, 1, 1), "## Sparse Attention\nfoo\n## RAG Pipelines\nbar"),
        (_dt.date(2026, 1, 2), "## Sparse Attention\nbaz"),
    ]
    result = _iq._stub_questions(week)
    # "Sparse Attention" was mentioned twice vs. "RAG Pipelines" once, so it
    # must be the topic slotted into the first (most_common) bank line.
    numbered = [l for l in result.split("\n") if re.match(r"^\d+\.", l)]
    assert "Sparse Attention" in numbered[0]


def test_stub_questions_falls_back_to_default_bank_when_no_headings():
    week = [(_dt.date(2026, 1, 1), "no headings in this digest")]
    result = _iq._stub_questions(week)
    for topic in ("Transformers", "RAG", "Quantization", "Agents", "Evaluation"):
        assert topic in result


def test_stub_questions_empty_week_falls_back_to_defaults():
    result = _iq._stub_questions([])
    assert "Transformers" in result


def test_stub_questions_caps_at_five_lines_even_with_more_topics():
    text = "\n".join(f"## Topic {i}" for i in range(10))
    week = [(_dt.date(2026, 1, 1), text)]
    result = _iq._stub_questions(week)
    numbered = [l for l in result.split("\n") if re.match(r"^\d+\.", l)]
    assert len(numbered) == 5
