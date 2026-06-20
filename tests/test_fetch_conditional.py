"""Conditional GET (ETag / Last-Modified) — skip unchanged feeds cheaply.

Two layers, all hermetic:

* low level ``_raw_conditional_get`` — builds the conditional request and turns
  an HTTP 304 into a ``NotModified`` signal (``urllib.request.urlopen`` patched).
* feed level ``fetch_feed(..., cache=...)`` / ``fetch_all(..., cache=...)`` —
  threads prior validators in, refreshes them on 200, and surfaces 304 as a
  ``NotModified`` so an accumulating consumer can skip the feed (the network
  seam ``_raw_conditional_get`` is patched).

Plus a JSON round-trip for the on-disk validator cache.
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import fetch as _fetch  # noqa: E402

RSS_OK = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><title>Hello</title><link>https://example.com/h</link>
    <description>world</description></item>
</channel></rss>"""


class _FakeResp:
    """Minimal stand-in for an http.client.HTTPResponse used as a CM."""

    def __init__(self, body: bytes, headers: dict[str, str]):
        self._body = body
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


# --------------------------------------------------------------------------- #
# Low level: _raw_conditional_get                                             #
# --------------------------------------------------------------------------- #
def test_conditional_get_sends_prior_validators(monkeypatch):
    """Given an etag + last-modified, the request carries If-None-Match and
    If-Modified-Since so the server can answer 304."""
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["if_none_match"] = req.get_header("If-none-match")
        seen["if_modified_since"] = req.get_header("If-modified-since")
        return _FakeResp(RSS_OK, {"ETag": '"new"', "Last-Modified": "Tue, 02"})

    monkeypatch.setattr(_fetch.urllib.request, "urlopen", fake_urlopen)

    _fetch._raw_conditional_get(
        "https://e/f", etag='"abc"', last_modified="Mon, 01"
    )
    assert seen["if_none_match"] == '"abc"'
    assert seen["if_modified_since"] == "Mon, 01"


def test_conditional_get_returns_body_and_fresh_validators(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return _FakeResp(RSS_OK, {"ETag": '"v2"', "Last-Modified": "Wed, 03"})

    monkeypatch.setattr(_fetch.urllib.request, "urlopen", fake_urlopen)

    body, etag, last_modified = _fetch._raw_conditional_get("https://e/f")
    assert body == RSS_OK
    assert etag == '"v2"'
    assert last_modified == "Wed, 03"


def test_conditional_get_304_raises_not_modified(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            url="https://e/f", code=304, msg="Not Modified", hdrs=None, fp=None
        )

    monkeypatch.setattr(_fetch.urllib.request, "urlopen", fake_urlopen)

    try:
        _fetch._raw_conditional_get("https://e/f", etag='"abc"')
    except _fetch.NotModified:
        pass
    else:
        raise AssertionError("expected NotModified on HTTP 304")


def test_conditional_get_other_http_error_propagates(monkeypatch):
    """A non-304 error is a real failure, not a not-modified signal."""
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            url="u", code=500, msg="Server Error", hdrs=None, fp=None
        )

    monkeypatch.setattr(_fetch.urllib.request, "urlopen", fake_urlopen)

    try:
        _fetch._raw_conditional_get("https://e/f")
    except urllib.error.HTTPError as e:
        assert e.code == 500
    else:
        raise AssertionError("expected HTTPError(500) to propagate")


# --------------------------------------------------------------------------- #
# Feed level: fetch_feed(cache=...)                                            #
# --------------------------------------------------------------------------- #
def test_fetch_feed_with_cache_refreshes_validators_on_200(monkeypatch):
    monkeypatch.setattr(
        _fetch,
        "_raw_conditional_get",
        lambda url, *, etag=None, last_modified=None: (RSS_OK, '"v2"', "Wed, 03"),
    )
    cache: dict[str, dict] = {}
    out = _fetch.fetch_feed(
        {"name": "x", "url": "https://e/f"}, top_n=1, cache=cache
    )
    assert out and out[0]["title"] == "Hello"
    assert cache["https://e/f"] == {"etag": '"v2"', "last_modified": "Wed, 03"}


def test_fetch_feed_with_cache_sends_prior_validators(monkeypatch):
    seen = {}

    def fake(url, *, etag=None, last_modified=None):
        seen["etag"] = etag
        seen["last_modified"] = last_modified
        return RSS_OK, '"fresh"', "Thu, 04"

    monkeypatch.setattr(_fetch, "_raw_conditional_get", fake)
    cache = {"https://e/f": {"etag": '"old"', "last_modified": "Mon, 01"}}
    _fetch.fetch_feed({"name": "x", "url": "https://e/f"}, top_n=1, cache=cache)
    assert seen["etag"] == '"old"'
    assert seen["last_modified"] == "Mon, 01"


def test_fetch_feed_with_cache_304_raises_and_leaves_cache(monkeypatch):
    def fake(url, *, etag=None, last_modified=None):
        raise _fetch.NotModified()

    monkeypatch.setattr(_fetch, "_raw_conditional_get", fake)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    prior = {"https://e/f": {"etag": '"keep"', "last_modified": "Mon, 01"}}
    cache = dict(prior)
    try:
        _fetch.fetch_feed({"name": "x", "url": "https://e/f"}, top_n=1, cache=cache)
    except _fetch.NotModified:
        pass
    else:
        raise AssertionError("expected NotModified to propagate from fetch_feed")
    assert cache == prior  # validators untouched on 304


def test_fetch_all_with_cache_carries_not_modified_payload(monkeypatch):
    def fake(url, *, etag=None, last_modified=None):
        if url.endswith("/stale"):
            raise _fetch.NotModified()
        return RSS_OK, '"v"', "Fri, 05"

    monkeypatch.setattr(_fetch, "_raw_conditional_get", fake)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    feeds = [
        {"name": "fresh", "url": "https://e/fresh"},
        {"name": "stale", "url": "https://e/stale"},
    ]
    cache: dict[str, dict] = {}
    out = _fetch.fetch_all(feeds, top_n=1, cache=cache)
    by_name = {f["name"]: payload for f, payload in out}

    assert isinstance(by_name["stale"], _fetch.NotModified)
    assert isinstance(by_name["fresh"], list) and by_name["fresh"]
    assert cache["https://e/fresh"] == {"etag": '"v"', "last_modified": "Fri, 05"}


# --------------------------------------------------------------------------- #
# On-disk validator cache                                                     #
# --------------------------------------------------------------------------- #
def test_feed_cache_file_roundtrip(tmp_path):
    path = tmp_path / "fetch-cache.json"
    data = {"https://e/f": {"etag": '"v1"', "last_modified": "Mon, 01"}}
    _fetch.save_feed_cache(path, data)
    assert _fetch.load_feed_cache(path) == data


def test_load_feed_cache_missing_returns_empty(tmp_path):
    assert _fetch.load_feed_cache(tmp_path / "nope.json") == {}
