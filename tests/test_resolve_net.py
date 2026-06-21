"""Shared resolver network helper ``_net.get_bytes`` — offline, hermetic.

Patches the genuine single-fetch seam ``_fetch._raw_http_get`` (the one
``_fetch._http_get`` wraps with retry/backoff). No sockets; ``time.sleep`` is a
no-op so retry/backoff never actually waits.
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import fetch as _fetch  # noqa: E402
from phantom_ai_feed.resolvers import _net  # noqa: E402


def test_get_bytes_returns_body_on_success(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: b"hello")
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _net.get_bytes("https://example.com/") == b"hello"


def test_get_bytes_returns_none_on_urlerror(monkeypatch):
    def boom(url):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(_fetch, "_raw_http_get", boom)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _net.get_bytes("https://example.com/") is None


def test_get_bytes_passes_max_retries(monkeypatch):
    """max_retries=0 means a single attempt: a retryable error is not retried."""
    calls = {"n": 0}

    def boom(url):
        calls["n"] += 1
        raise TimeoutError("slow")  # retryable, but budget is 0

    monkeypatch.setattr(_fetch, "_raw_http_get", boom)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _net.get_bytes("https://example.com/", max_retries=0) is None
    assert calls["n"] == 1
