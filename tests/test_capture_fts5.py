"""P1.3 — FTS5 capture adapter (unit, fully OFFLINE).

The adapter folds an entry into a single text blob and captures it into the
phantom FTS5 knowledge base via the `phantom event capture` CLI seam. These
tests stub the CLI seam entirely (monkeypatched ``shutil.which`` +
``subprocess.run``); no real ``phantom`` binary is invoked.

Three branches are covered:
  1. no CLI on PATH   → CaptureResult(status="no-cli"), subprocess never called
  2. CLI present, fails → CaptureResult(status="error"), stderr surfaced
  3. CLI present, ok    → CaptureResult(status="ok")

Plus a ``dry_run`` flag that BUILDS the command (returnable for inspection)
without ever executing it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import capture as _cap  # noqa: E402

ENTRY = {
    "title": "New sparse-attention transformer",
    "summary": "繁中 summary: 38% less KV-cache on a 70B model.",
    "link": "https://example.com/a",
    "source": "arxiv-cs-AI",
}


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --------------------------------------------------------------------------- #
# build_capture_command — pure, no I/O                                        #
# --------------------------------------------------------------------------- #
def test_build_command_folds_entry_into_one_blob():
    cmd = _cap.build_capture_command(ENTRY)
    assert cmd[:4] == ["phantom", "event", "capture", "--kind"]
    assert "ai-feed" in cmd
    assert "--text" in cmd
    text = cmd[cmd.index("--text") + 1]
    # all four fields folded into the single text blob
    assert "New sparse-attention transformer" in text
    assert "38% less KV-cache" in text
    assert "https://example.com/a" in text
    assert "source: arxiv-cs-AI" in text


def test_build_command_truncates_to_2000_chars():
    big = {"title": "x" * 5000, "summary": "y" * 5000, "link": "", "source": "s"}
    cmd = _cap.build_capture_command(big)
    text = cmd[cmd.index("--text") + 1]
    assert len(text) <= 2000


def test_build_command_skips_empty_fields():
    cmd = _cap.build_capture_command(
        {"title": "Only a title", "summary": "", "link": "", "source": ""}
    )
    text = cmd[cmd.index("--text") + 1]
    assert "Only a title" in text
    # empty source still annotated with a default rather than "source: "
    assert "source: " in text


# --------------------------------------------------------------------------- #
# branch 1: no CLI on PATH                                                     #
# --------------------------------------------------------------------------- #
def test_no_cli_returns_no_cli_without_calling_subprocess(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(_cap.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        _cap.subprocess, "run",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )
    res = _cap.capture_entry(ENTRY, backend="phantom")
    assert res.status == "no-cli"
    assert res.ok is False
    assert called["n"] == 0  # subprocess NEVER invoked


# --------------------------------------------------------------------------- #
# branch 2: CLI present but fails                                             #
# --------------------------------------------------------------------------- #
def test_cli_failure_returns_error_with_stderr(monkeypatch):
    monkeypatch.setattr(_cap.shutil, "which", lambda _name: "/usr/bin/phantom")

    def boom(*a, **k):
        return _FakeProc(returncode=1, stderr="db locked: try again")

    monkeypatch.setattr(_cap.subprocess, "run", boom)
    res = _cap.capture_entry(ENTRY, backend="phantom")
    assert res.status == "error"
    assert res.ok is False
    assert "db locked" in (res.detail or "")


def test_cli_oserror_returns_error(monkeypatch):
    monkeypatch.setattr(_cap.shutil, "which", lambda _name: "/usr/bin/phantom")

    def raise_os(*a, **k):
        raise OSError("exec format error")

    monkeypatch.setattr(_cap.subprocess, "run", raise_os)
    res = _cap.capture_entry(ENTRY, backend="phantom")
    assert res.status == "error"
    assert res.ok is False
    assert "exec format error" in (res.detail or "")


def test_cli_timeout_returns_error(monkeypatch):
    monkeypatch.setattr(_cap.shutil, "which", lambda _name: "/usr/bin/phantom")

    def slow(*a, **k):
        raise subprocess.TimeoutExpired(cmd="phantom", timeout=5)

    monkeypatch.setattr(_cap.subprocess, "run", slow)
    res = _cap.capture_entry(ENTRY, backend="phantom")
    assert res.status == "error"
    assert res.ok is False


# --------------------------------------------------------------------------- #
# branch 3: CLI present and succeeds                                          #
# --------------------------------------------------------------------------- #
def test_cli_ok_returns_ok(monkeypatch):
    seen = {}
    monkeypatch.setattr(_cap.shutil, "which", lambda _name: "/usr/bin/phantom")

    def run_ok(cmd, *a, **k):
        seen["cmd"] = cmd
        return _FakeProc(returncode=0, stdout="captured 1 event")

    monkeypatch.setattr(_cap.subprocess, "run", run_ok)
    res = _cap.capture_entry(ENTRY, backend="phantom")
    assert res.status == "ok"
    assert res.ok is True
    # the executed command is exactly the one build_capture_command produces
    assert seen["cmd"] == _cap.build_capture_command(ENTRY)


# --------------------------------------------------------------------------- #
# dry_run: build the command without executing                                #
# --------------------------------------------------------------------------- #
def test_dry_run_builds_command_without_executing(monkeypatch):
    called = {"n": 0}
    # which present so we prove dry_run is what short-circuits, not absence of CLI
    monkeypatch.setattr(_cap.shutil, "which", lambda _name: "/usr/bin/phantom")
    monkeypatch.setattr(
        _cap.subprocess, "run",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )
    res = _cap.capture_entry(ENTRY, dry_run=True)
    assert res.status == "dry-run"
    assert res.ok is True  # building succeeded; nothing to fail
    assert res.command == _cap.build_capture_command(ENTRY)
    assert called["n"] == 0  # NEVER executed


def test_capture_many_aggregates_statuses(monkeypatch):
    monkeypatch.setattr(_cap.shutil, "which", lambda _name: "/usr/bin/phantom")
    monkeypatch.setattr(
        _cap.subprocess, "run", lambda *a, **k: _FakeProc(returncode=0)
    )
    results = _cap.capture_many([ENTRY, ENTRY, ENTRY], backend="phantom")
    assert len(results) == 3
    assert all(r.ok for r in results)


# --------------------------------------------------------------------------- #
# default backend = local SQLite FTS5 (no daemon)                             #
# --------------------------------------------------------------------------- #
def test_default_backend_writes_to_local_store(tmp_path):
    """capture_entry() with no backend arg writes to the local SQLite store and
    is immediately recallable — no phantom daemon involved."""
    from phantom_ai_feed import store as _store

    db = tmp_path / "k.db"
    res = _cap.capture_entry(
        {"title": "Mixture of Experts routing", "summary_excerpt": "sparse MoE",
         "link": "http://e/moe", "source": "arxiv", "category": "research"},
        db_path=db,
    )
    assert res.status == "ok" and res.ok
    rows = _store.recall("experts", db_path=db)
    assert rows and rows[0]["link"] == "http://e/moe"


def test_local_backend_dry_run_writes_nothing(tmp_path):
    db = tmp_path / "k.db"
    res = _cap.capture_entry({"title": "x", "link": "l", "source": "s"}, db_path=db, dry_run=True)
    assert res.status == "dry-run"
    assert not db.exists()  # nothing written
