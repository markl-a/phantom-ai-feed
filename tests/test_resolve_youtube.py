"""YouTube channel-id resolver — offline, hermetic tests.

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
from phantom_ai_feed.resolvers import youtube as _yt  # noqa: E402

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
UCID = "UCXuqSBlHAE6Xw-yeJA0Tunw"

HTML_WITH_EXTERNAL_ID = (
    b'<html><head><script>var ytcfg={"a":1};'
    b'window.ytInitialData={"externalId":"' + UCID.encode() + b'","b":2};'
    b'</script></head><body>hi</body></html>'
)

HTML_WITH_CANONICAL_ONLY = (
    b'<html><head>'
    b'<link rel="canonical" href="https://www.youtube.com/channel/'
    + UCID.encode() + b'">'
    b'</head><body>no external id here</body></html>'
)

HTML_WITH_NEITHER = b"<html><head><title>nope</title></head><body>none</body></html>"


# --------------------------------------------------------------------------- #
# channel_feed_url                                                            #
# --------------------------------------------------------------------------- #
def test_channel_feed_url_formats_correctly():
    assert _yt.channel_feed_url(UCID) == (
        "https://www.youtube.com/feeds/videos.xml?channel_id=" + UCID
    )


# --------------------------------------------------------------------------- #
# resolve_channel_id — extraction                                            #
# --------------------------------------------------------------------------- #
def test_external_id_present_resolves(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: HTML_WITH_EXTERNAL_ID)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _yt.resolve_channel_id("@SomeHandle") == UCID


def test_canonical_fallback_resolves(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: HTML_WITH_CANONICAL_ONLY)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _yt.resolve_channel_id("SomeHandle") == UCID


def test_neither_present_returns_none(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: HTML_WITH_NEITHER)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert _yt.resolve_channel_id("@SomeHandle") is None


# --------------------------------------------------------------------------- #
# resolve_channel_id — cache behaviour                                        #
# --------------------------------------------------------------------------- #
def test_cache_hit_skips_network(monkeypatch):
    calls = {"n": 0}

    def counting_get(url):
        calls["n"] += 1
        return HTML_WITH_EXTERNAL_ID

    monkeypatch.setattr(_fetch, "_raw_http_get", counting_get)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    cache = {"SomeHandle": "UCcached0000000000000000"}
    # Leading '@' is normalised away before the lookup.
    out = _yt.resolve_channel_id("@SomeHandle", cache=cache)
    assert out == "UCcached0000000000000000"
    assert calls["n"] == 0  # never touched the network


def test_cache_miss_populates_cache(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: HTML_WITH_EXTERNAL_ID)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    cache: dict = {}
    out = _yt.resolve_channel_id("@SomeHandle", cache=cache)
    assert out == UCID
    # Stored under the normalised handle (no leading '@').
    assert cache == {"SomeHandle": UCID}


# --------------------------------------------------------------------------- #
# resolve_channel_id — network failure                                        #
# --------------------------------------------------------------------------- #
def test_network_error_returns_none(monkeypatch):
    def boom(url):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(_fetch, "_raw_http_get", boom)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    assert _yt.resolve_channel_id("@SomeHandle") is None
