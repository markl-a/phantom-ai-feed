"""Podcast RSS resolver (iTunes lookup/search API) — offline, hermetic tests.

All network is patched at the seam: ``_fetch._raw_http_get`` (the genuine
single fetch that ``_fetch._http_get`` wraps with retry/backoff). No sockets are
opened; ``time.sleep`` is stubbed so retry/backoff never actually waits.
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import fetch as _fetch  # noqa: E402
from phantom_ai_feed.resolvers import podcast as _pod  # noqa: E402

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
FEED_URL = "https://x/feed.rss"

LOOKUP_ONE = b'{"resultCount":1,"results":[{"feedUrl":"https://x/feed.rss"}]}'

SEARCH_TWO = (
    b'{"resultCount":2,"results":['
    b'{"feedUrl":"https://x/first.rss"},'
    b'{"feedUrl":"https://x/second.rss"}]}'
)

EMPTY = b'{"resultCount":0,"results":[]}'

# First result has no feedUrl; the second does — resolver should skip to it.
MISSING_THEN_PRESENT = (
    b'{"resultCount":2,"results":['
    b'{"trackName":"no feed here"},'
    b'{"feedUrl":"https://x/second.rss"}]}'
)


# --------------------------------------------------------------------------- #
# resolve_feed — happy paths                                                  #
# --------------------------------------------------------------------------- #
def test_lookup_by_apple_id_returns_feed_url(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: LOOKUP_ONE)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _pod.resolve_feed(apple_id=1469999563) == FEED_URL


def test_search_by_term_returns_first_result(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: SEARCH_TWO)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _pod.resolve_feed(term="Latent Space") == "https://x/first.rss"


# --------------------------------------------------------------------------- #
# resolve_feed — URL construction                                             #
# --------------------------------------------------------------------------- #
def test_lookup_url_contains_apple_id(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        _fetch, "_raw_http_get", lambda url: (seen.__setitem__("url", url), LOOKUP_ONE)[1]
    )
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    _pod.resolve_feed(apple_id=1469999563)
    assert "itunes.apple.com/lookup" in seen["url"]
    assert "id=1469999563" in seen["url"]
    assert "entity=podcast" in seen["url"]


def test_search_url_url_quotes_term(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        _fetch, "_raw_http_get", lambda url: (seen.__setitem__("url", url), SEARCH_TWO)[1]
    )
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    _pod.resolve_feed(term="Latent Space")
    assert "itunes.apple.com/search" in seen["url"]
    # space is url-quoted (quote() -> %20), not left raw.
    assert "Latent%20Space" in seen["url"]
    assert "Latent Space" not in seen["url"]
    assert "entity=podcast" in seen["url"]
    assert "limit=1" in seen["url"]


# --------------------------------------------------------------------------- #
# resolve_feed — empty / missing                                             #
# --------------------------------------------------------------------------- #
def test_empty_results_returns_none(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: EMPTY)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _pod.resolve_feed(apple_id=42) is None


def test_first_result_missing_feed_url_skips_to_next(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: MISSING_THEN_PRESENT)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _pod.resolve_feed(term="whatever") == "https://x/second.rss"


# --------------------------------------------------------------------------- #
# resolve_feed — bad usage RAISES (not swallowed)                             #
# --------------------------------------------------------------------------- #
def test_neither_apple_id_nor_term_raises():
    try:
        _pod.resolve_feed()
    except ValueError as e:
        assert "apple_id or term required" in str(e)
    else:
        raise AssertionError("expected ValueError when given neither arg")


# --------------------------------------------------------------------------- #
# resolve_feed — JSON / network errors are swallowed -> None                  #
# --------------------------------------------------------------------------- #
def test_malformed_json_returns_none(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: b"not json")
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _pod.resolve_feed(apple_id=1) is None


def test_network_error_returns_none(monkeypatch):
    def boom(url):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(_fetch, "_raw_http_get", boom)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _pod.resolve_feed(term="anything") is None
