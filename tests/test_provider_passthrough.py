"""PHANTOM_PROVIDER passthrough for `phantom exec`.

When the env var ``PHANTOM_PROVIDER`` is set and non-empty, ``summarize_phantom``
must inject ``--provider <value>`` into the argv right after ``exec``. When it
is unset (or empty/whitespace), the argv must be unchanged:
``["phantom", "exec", <prompt>]``.

The real ``subprocess.run`` is monkeypatched so the test is fully offline and
captures the exact argv that would cross the transport boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import summarize as _sum  # noqa: E402


class _FakeProc:
    """Stand-in for subprocess.CompletedProcess."""

    returncode = 0
    stdout = "fake llm body"
    stderr = ""


def _patch_phantom(monkeypatch, captured):
    def fake_run(argv, *args, **kwargs):
        captured["argv"] = list(argv)
        return _FakeProc()

    monkeypatch.setattr(_sum.subprocess, "run", fake_run)
    monkeypatch.setattr(_sum.shutil, "which", lambda _name: "/usr/bin/phantom")


def test_provider_injected_when_env_set(monkeypatch):
    captured: dict[str, list[str]] = {}
    _patch_phantom(monkeypatch, captured)
    monkeypatch.setenv("PHANTOM_PROVIDER", "openrouter")

    out = _sum.summarize_phantom("hello world", max_words=40)
    assert out == "fake llm body"

    argv = captured["argv"]
    assert argv[0] == "phantom"
    assert argv[1] == "exec"
    # --provider <value> must appear immediately after "exec".
    assert argv[2] == "--provider"
    assert argv[3] == "openrouter"
    assert "--provider" in argv
    # Prompt is still the final positional arg.
    assert argv[-1] != "--provider"
    assert argv[-2] == "openrouter"


def test_provider_absent_when_env_unset(monkeypatch):
    captured: dict[str, list[str]] = {}
    _patch_phantom(monkeypatch, captured)
    monkeypatch.delenv("PHANTOM_PROVIDER", raising=False)

    _sum.summarize_phantom("hello world", max_words=40)

    argv = captured["argv"]
    assert "--provider" not in argv
    assert argv[0] == "phantom"
    assert argv[1] == "exec"
    assert len(argv) == 3  # phantom, exec, prompt — unchanged


def test_provider_empty_or_whitespace_leaves_argv_unchanged(monkeypatch):
    for val in ("", "   "):
        captured: dict[str, list[str]] = {}
        _patch_phantom(monkeypatch, captured)
        monkeypatch.setenv("PHANTOM_PROVIDER", val)

        _sum.summarize_phantom("hello world", max_words=40)

        argv = captured["argv"]
        assert "--provider" not in argv, f"empty/whitespace {val!r} must not inject"
        assert len(argv) == 3
