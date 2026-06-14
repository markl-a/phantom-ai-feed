"""Offline stub-path tests for the three writers: digest render, weekly
analysis, and the weekend interview-question generator.

All deterministic, no network, no LLM. They exercise the same code paths the
committed docs/sample-*.md files were generated from.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import digest as _digest  # noqa: E402
from phantom_ai_feed import interview_questions as _iq  # noqa: E402
from phantom_ai_feed import weekly as _weekly  # noqa: E402


def test_digest_render_stub_path():
    """_render with stub=True tags the stub badge and lays out entries +
    error sections as Markdown."""
    date = _dt.date(2026, 6, 14)
    sections = [
        (
            {"name": "research", "category": "research", "url": "file:///x.xml"},
            [{"title": "SparseMoE-7B", "link": "https://example.org/p", "summary": "synthetic summary"}],
        ),
        (
            {"name": "broken-feed", "category": "blog", "url": "file:///y.xml"},
            "URLError: synthetic failure",  # error payload is a str
        ),
    ]
    md = _digest._render(date, sections, stub=True)
    assert "phantom-ai-feed digest — 2026-06-14" in md
    assert "stub-summarizer" in md  # badge reflects the stub path
    assert "gemini-flash" not in md
    assert "**[SparseMoE-7B](https://example.org/p)**" in md
    assert "synthetic summary" in md
    assert "> ERROR: URLError: synthetic failure" in md  # error section rendered


def test_interview_questions_stub_path(tmp_path):
    """run(use_stub=True) reads daily digests, templates one question per top
    topic from the '## heading' lines, and writes a weekly-questions file."""
    end = _dt.date(2026, 6, 14)
    digest = (
        "# digest\n\n"
        "## Quantization  _(category: blog)_\n- item\n\n"
        "## RAG-evaluation  _(category: research)_\n- item\n"
    )
    (tmp_path / f"{end.isoformat()}.md").write_text(digest, encoding="utf-8")

    out = _iq.run(log_dir=tmp_path, end=end, use_stub=True)

    assert out.name == f"weekly-questions-{end.isoformat()}.md"
    body = out.read_text("utf-8")
    assert "Stub generator" in body
    # one templated question per topic heading found in the digest
    assert "Explain Quantization" in body
    assert "RAG-evaluation" in body
    assert body.strip().splitlines()[-1].startswith("2.")  # exactly 2 topics -> 2 questions


def test_interview_questions_stub_no_digests(tmp_path):
    """With no digest files the generator still writes a file with an honest
    'no digest files' note instead of fabricating questions."""
    end = _dt.date(2026, 6, 14)
    out = _iq.run(log_dir=tmp_path, end=end, use_stub=True)
    assert "no digest files" in out.read_text("utf-8")


def test_weekly_analyze_stub_path():
    """_analyze with use_stub=True returns an extractive body + the
    'stub-extractive' badge, never pretending an LLM ran."""
    blob = (
        "- [research] SparseMoE-7B matches dense 13B at half the FLOPs. "
        "It routes tokens to 2 of 16 experts. Second sentence here."
    )
    body, badge = _weekly._analyze(blob, use_stub=True)
    assert badge == "stub-extractive"
    assert body  # non-empty extractive summary
    assert "SparseMoE-7B" in body
