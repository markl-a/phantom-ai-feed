"""P1.1 — prompt double-wrapping regression guard.

The weekly-digest and interview-question runs each assemble a *fully-formed*
LLM prompt of their own. Those must reach the model verbatim. The bug: they
were routed through ``summarize`` / ``summarize_phantom``, which internally
re-wrap their argument with the per-article DAILY-summary preamble
(``_build_prompt``: "Summarise the following article in ≤N words … ARTICLE:").
That double-wraps a weekly/interview prompt inside a "summarise one article"
instruction — the wrong payload to the LLM.

These tests capture the EXACT prompt bytes that cross the *real* transport
boundary (``subprocess.run`` for ``phantom exec``; ``urllib`` for Gemini —
both monkeypatched, fully offline) so that any internal ``_build_prompt``
wrapping has already been applied by the time we inspect the payload. Then we
assert the daily preamble is absent while the run's own instructions survive.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import interview_questions as iq  # noqa: E402
from phantom_ai_feed import summarize as _sum  # noqa: E402
from phantom_ai_feed import weekly  # noqa: E402

# Fragments that uniquely identify the DAILY per-article preamble (_build_prompt).
# If any of these appear in a weekly/interview payload, it was double-wrapped.
DAILY_PREAMBLE_MARKERS = (
    "Summarise the following article",
    "\n\nARTICLE:\n",
    "Output the summary only, no preamble.",
)


def _daily_preamble_present(prompt: str) -> bool:
    return any(m in prompt for m in DAILY_PREAMBLE_MARKERS)


class _FakeProc:
    """Stand-in for subprocess.CompletedProcess."""

    returncode = 0
    stdout = "## 本週趨勢\nfake llm body"
    stderr = ""


def _patch_phantom_transport(monkeypatch, captured):
    """Patch the genuine `phantom exec` transport so _build_prompt has run by
    the time we capture argv. Returns nothing; fills captured['prompt']."""

    def fake_run(argv, *args, **kwargs):
        # argv = ["phantom", "exec", <FINAL PROMPT STRING>]
        captured["prompt"] = argv[2]
        return _FakeProc()

    monkeypatch.setattr(_sum.subprocess, "run", fake_run)
    monkeypatch.setattr(_sum.shutil, "which", lambda _name: "/usr/bin/phantom")


# --------------------------------------------------------------------------- #
# Weekly digest                                                               #
# --------------------------------------------------------------------------- #
def test_weekly_prompt_is_not_double_wrapped(monkeypatch):
    """The blob handed to phantom exec for the weekly run must be EXACTLY the
    weekly prompt — no daily-summary preamble bolted on the front/back."""
    captured: dict[str, str] = {}
    _patch_phantom_transport(monkeypatch, captured)
    # weekly._analyze gates on its own module's shutil.which too.
    monkeypatch.setattr(weekly.shutil, "which", lambda _name: "/usr/bin/phantom")

    entries = [
        {"title": "Sparse attention at 1/3 cost", "source": "arxiv-cs-AI",
         "summary_excerpt": "A 70B model with 38% less KV-cache memory."},
        {"title": "Agentic eval harness", "source": "hacker-news-frontpage",
         "summary_excerpt": "Closed-loop scoring for tool-use agents."},
    ]
    blob = weekly._build_blob(entries)
    body, badge = weekly._analyze(blob, use_stub=False)

    assert badge == "phantom-exec"
    assert "prompt" in captured, "transport was never called"
    prompt = captured["prompt"]

    # The weekly prompt's own instructions must be present and intact.
    assert "WEEKLY digest" in prompt
    assert "=== RAW FEED ITEMS ===" in prompt
    assert "Sparse attention at 1/3 cost" in prompt  # the actual blob made it

    # ...and the daily per-article preamble must NOT be wrapped around it.
    assert not _daily_preamble_present(prompt), (
        "weekly prompt was double-wrapped with the daily-summary preamble:\n"
        + prompt[:400]
    )

    # Byte-exact: the captured prompt is exactly the weekly prompt builder output.
    assert prompt == weekly._build_weekly_prompt(blob)


# --------------------------------------------------------------------------- #
# Interview questions                                                          #
# --------------------------------------------------------------------------- #
def test_interview_prompt_is_not_double_wrapped(monkeypatch, tmp_path):
    """The interview-question run builds its own hiring-manager prompt; the
    bytes reaching the LLM must omit the daily-summary preamble."""
    captured: dict[str, str] = {}
    # Route via phantom exec (the dispatcher prefers it when on PATH).
    _patch_phantom_transport(monkeypatch, captured)

    # Seed a week of fake digest files so _collect_week returns content.
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    end = _dt.date(2026, 6, 13)
    for i in range(3):
        d = end - _dt.timedelta(days=i)
        (log_dir / f"{d.isoformat()}.md").write_text(
            f"# digest {d}\n## RAG\n- retrieval augmented generation news\n",
            encoding="utf-8",
        )

    # use_stub=False but force the LLM branch by setting a key (run() gates on it).
    monkeypatch.setenv("GEMINI_API_KEY", "FAKE_DO_NOT_CALL")
    iq.run(log_dir=log_dir, end=end, use_stub=False)

    assert "prompt" in captured, "transport was never called"
    prompt = captured["prompt"]

    # The interview prompt's own instructions must be present and intact.
    assert "You are an ML hiring manager." in prompt
    assert "=== WEEK DIGEST ===" in prompt
    assert "retrieval augmented generation news" in prompt  # the week blob made it

    # ...and the daily per-article preamble must NOT be wrapped around it.
    assert not _daily_preamble_present(prompt), (
        "interview prompt was double-wrapped with the daily-summary preamble:\n"
        + prompt[:400]
    )

    # Byte-exact: exactly the interview prompt builder output for this week.
    week = iq._collect_week(log_dir, end)
    assert prompt == iq._llm_prompt(week)


# --------------------------------------------------------------------------- #
# The daily path must STILL wrap (don't over-correct).                        #
# --------------------------------------------------------------------------- #
def test_daily_summarize_still_wraps_raw_article(monkeypatch):
    """Guard against over-correcting: a raw article passed to summarize() for
    the DAILY digest must still receive the per-article preamble."""
    captured: dict[str, str] = {}
    _patch_phantom_transport(monkeypatch, captured)

    _sum.summarize("OpenAI shipped a new model with 40% lower latency.",
                   use_stub=False)

    assert "prompt" in captured
    assert _daily_preamble_present(captured["prompt"]), (
        "daily summarize() must still wrap a raw article with the preamble"
    )
    assert "OpenAI shipped a new model" in captured["prompt"]


def test_daily_gemini_also_wraps_raw_article(monkeypatch):
    """Same guard via the Gemini transport: the request body the dispatcher
    sends for a daily article must contain the per-article preamble."""
    captured: dict[str, str] = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
            ).encode("utf-8")

    def fake_urlopen(req, timeout=None):
        body = req.data.decode("utf-8")
        payload = json.loads(body)
        captured["prompt"] = payload["contents"][0]["parts"][0]["text"]
        return _Resp()

    monkeypatch.setattr(_sum.urllib.request, "urlopen", fake_urlopen)
    # No phantom on PATH → dispatcher goes straight to Gemini with the key.
    monkeypatch.setattr(_sum.shutil, "which", lambda _name: None)

    _sum.summarize("A new RAG benchmark dropped today.",
                   use_stub=False, api_key="FAKE_KEY")

    assert "prompt" in captured
    assert _daily_preamble_present(captured["prompt"])
    assert "A new RAG benchmark dropped today." in captured["prompt"]
