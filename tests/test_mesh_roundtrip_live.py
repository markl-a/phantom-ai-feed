from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import capture as cap  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("phantom") is None, reason="needs real phantom binary"
)


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_healthz(port: int, timeout_s: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout_s
    url = f"http://127.0.0.1:{port}/healthz"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if 200 <= response.status < 300:
                    return True
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    return False


def _terminate_daemon(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=5)


def _recall(query: str, env: dict[str, str]) -> list[dict]:
    proc = subprocess.run(
        ["phantom", "recall", query, "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    # `phantom recall --json` prints a JSON array on a hit but an empty/blank
    # stdout when the store has zero matches (build-dependent) — treat that as
    # the empty result set rather than letting json.loads choke on "".
    out = (proc.stdout or "").strip()
    return json.loads(out) if out else []


@pytest.mark.live
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="cannot isolate phantom store on Windows (dirs::home_dir ignores HOME)",
)
def test_capture_then_recall_roundtrip_live(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("cannot isolate phantom store on Windows (dirs::home_dir ignores HOME)")

    home = tmp_path
    mesh_dir = home / ".phantom-mesh"
    mesh_dir.mkdir(parents=True)
    (mesh_dir / "identity.key").write_bytes(os.urandom(64))

    port = _free_tcp_port()
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PHANTOM_PORT"] = str(port)

    daemon = subprocess.Popen(
        ["phantom", "serve"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        if not _wait_for_healthz(port):
            _terminate_daemon(daemon)
            pytest.skip("phantom serve did not start")

        token = "Opus"
        entry = {
            "title": "Anthropic ships Opus 4.8",
            "summary": "New model with 1M context window and faster output.",
            "link": "https://example.com/opus48",
            "source": "phantom-ai-feed",
        }

        assert _recall(token, env) == []

        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("PHANTOM_PORT", str(port))

        result = cap.capture_entry(entry)
        detail = (result.detail or "").lower()
        provider_terms = ("provider", "auth", "503", "api_key", "api key", "not set")
        if result.status == "error" and any(term in detail for term in provider_terms):
            pytest.skip("no LLM provider configured for phantom daemon")
        assert result.status == "ok", result.detail

        hits = []
        for _ in range(10):
            hits = _recall(token, env)
            if hits:
                break
            time.sleep(0.5)

        assert len(hits) >= 1
        assert any(
            any(
                phrase in (hit.get("summary") or "").lower()
                for phrase in ("opus", "1m context", "model")
            )
            for hit in hits
        )
    finally:
        _terminate_daemon(daemon)
