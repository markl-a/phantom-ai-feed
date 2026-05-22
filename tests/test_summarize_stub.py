"""Stub summarizer must be deterministic and non-empty."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed.summarize import summarize, summarize_stub  # noqa: E402


SAMPLE = (
    "Researchers at OpenAI announced a new sparse-attention transformer that "
    "matches GPT-4 quality at 1/3 the inference cost. The paper claims a 38% "
    "reduction in KV-cache memory on a 70B model. Benchmarks include MMLU, "
    "GSM8K, and a new internal RAG eval. Code is not yet open-sourced."
)


def test_stub_nonempty_under_word_limit():
    out = summarize_stub(SAMPLE, max_words=30)
    assert out
    assert len(out.split()) <= 31  # cap + the "…" tail token


def test_stub_handles_empty():
    assert summarize_stub("", max_words=50) == "(no content)"
    assert summarize_stub("   ", max_words=50) == "(no content)"


def test_dispatcher_forces_stub_even_with_env_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "FAKE_DO_NOT_CALL")
    out = summarize(SAMPLE, use_stub=True, max_words=40)
    assert out
    assert "OpenAI" in out or "sparse-attention" in out


def test_dispatcher_no_key_falls_back():
    # Explicit empty api_key + no use_stub → still stub (defensive)
    out = summarize(SAMPLE, api_key="", use_stub=False, max_words=40)
    assert out
    assert out != "(no content)"
