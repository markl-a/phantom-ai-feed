"""Generic website RSS/Atom feed auto-discovery resolver (fully OFFLINE).

All tests are hermetic: the genuine single-fetch seam ``_fetch._raw_http_get``
is monkeypatched to return canned bytes keyed by URL, and ``time.sleep`` is a
no-op so the retry/backoff wrapper never actually waits. No sockets are opened.

Covers:
- <link rel="alternate"> discovery (relative + absolute href resolution).
- Multiple alternates (rss + atom): order-preserved, de-duped.
- Path-probing fallback when no <link> tags are present.
- All-non-feed probes -> [].
- Page fetch error -> [].
- _looks_like_feed truth table.
- Wrong rel / wrong type ignored.
"""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import fetch as _fetch  # noqa: E402
from phantom_ai_feed.resolvers import discover  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _install(monkeypatch, pages: dict[str, bytes]):
    """Patch the network seam with a canned URL->bytes map.

    A URL absent from ``pages`` raises HTTPError 404 (a non-feed / missing
    candidate), mirroring how a real server would answer an unknown probe path.
    """
    def fake_get(url: str) -> bytes:
        if url in pages:
            return pages[url]
        raise urllib.error.HTTPError(
            url=url, code=404, msg="Not Found", hdrs=None, fp=None
        )

    monkeypatch.setattr(_fetch, "_raw_http_get", fake_get)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)


FEED_XML = b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
NOT_FEED_HTML = b"<!doctype html><html><head><title>x</title></head></html>"


# --------------------------------------------------------------------------- #
# 1. <link rel=alternate> discovery                                           #
# --------------------------------------------------------------------------- #
def test_single_alternate_relative_href_resolved(monkeypatch):
    page = (
        b'<html><head>'
        b'<link rel="alternate" type="application/rss+xml" href="/feed.xml">'
        b'</head><body></body></html>'
    )
    _install(monkeypatch, {"https://example.com/": page})
    out = discover.discover_feeds("https://example.com/")
    assert out == ["https://example.com/feed.xml"]


def test_relative_and_absolute_hrefs_both_resolved(monkeypatch):
    page = (
        b'<html><head>'
        b'<link rel="alternate" type="application/rss+xml" href="rss.xml">'
        b'<link rel="alternate" type="application/atom+xml" '
        b'href="https://cdn.example.org/atom.xml">'
        b'</head></html>'
    )
    _install(monkeypatch, {"https://example.com/blog/": page})
    out = discover.discover_feeds("https://example.com/blog/")
    assert out == [
        "https://example.com/blog/rss.xml",
        "https://cdn.example.org/atom.xml",
    ]


def test_multiple_alternates_order_preserved_and_deduped(monkeypatch):
    page = (
        b'<html><head>'
        b'<link rel="alternate" type="application/rss+xml" href="/feed">'
        b'<link rel="alternate" type="application/atom+xml" href="/atom">'
        # duplicate of the first -> must be dropped, order preserved.
        b'<link rel="alternate" type="application/rss+xml" href="/feed">'
        b'</head></html>'
    )
    _install(monkeypatch, {"https://example.com/": page})
    out = discover.discover_feeds("https://example.com/")
    assert out == ["https://example.com/feed", "https://example.com/atom"]


def test_json_feed_types_discovered(monkeypatch):
    page = (
        b'<html><head>'
        b'<link rel="alternate" type="application/json" href="/feed.json">'
        b'<link rel="alternate" type="application/feed+json" href="/f2.json">'
        b'</head></html>'
    )
    _install(monkeypatch, {"https://example.com/": page})
    out = discover.discover_feeds("https://example.com/")
    assert out == [
        "https://example.com/feed.json",
        "https://example.com/f2.json",
    ]


def test_case_insensitive_rel_and_type(monkeypatch):
    page = (
        b'<html><head>'
        b'<LINK REL="ALTERNATE" TYPE="Application/RSS+XML" href="/feed.xml">'
        b'</head></html>'
    )
    _install(monkeypatch, {"https://example.com/": page})
    out = discover.discover_feeds("https://example.com/")
    assert out == ["https://example.com/feed.xml"]


def test_wrong_rel_or_wrong_type_ignored(monkeypatch):
    page = (
        b'<html><head>'
        b'<link rel="stylesheet" type="text/css" href="/style.css">'
        b'<link rel="alternate" type="text/html" href="/print">'
        b'<link rel="icon" href="/favicon.ico">'
        # the only genuine feed:
        b'<link rel="alternate" type="application/rss+xml" href="/real.xml">'
        b'</head></html>'
    )
    _install(monkeypatch, {"https://example.com/": page})
    out = discover.discover_feeds("https://example.com/")
    assert out == ["https://example.com/real.xml"]


# --------------------------------------------------------------------------- #
# 2. Path-probing fallback                                                     #
# --------------------------------------------------------------------------- #
def test_probe_fallback_finds_single_valid_candidate(monkeypatch):
    # No <link> tags. "/feed" is a real feed; every other probe path 404s.
    page = b"<html><head><title>no feeds here</title></head><body></body></html>"
    _install(monkeypatch, {
        "https://example.com/": page,
        "https://example.com/feed": FEED_XML,
    })
    out = discover.discover_feeds("https://example.com/")
    assert out == ["https://example.com/feed"]


def test_probe_fallback_all_non_feed_returns_empty(monkeypatch):
    # No <link> tags, and every probe path returns non-feed HTML (not a 404,
    # an actual 200 of HTML) -> nothing validates.
    page = b"<html><head></head><body>home</body></html>"
    pages = {"https://example.com/": page}
    for path in (
        "/feed", "/rss", "/rss.xml", "/atom.xml", "/feed.xml",
        "/index.xml", "/feed/", "/?feed=rss2",
    ):
        pages["https://example.com" + path] = NOT_FEED_HTML
    _install(monkeypatch, pages)
    out = discover.discover_feeds("https://example.com/")
    assert out == []


# --------------------------------------------------------------------------- #
# 3. Network error on the page fetch                                           #
# --------------------------------------------------------------------------- #
def test_page_fetch_urlerror_returns_empty(monkeypatch):
    def boom(url):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(_fetch, "_raw_http_get", boom)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    assert discover.discover_feeds("https://example.com/") == []


# --------------------------------------------------------------------------- #
# 4. _looks_like_feed truth table                                             #
# --------------------------------------------------------------------------- #
def test_looks_like_feed_truth_table():
    assert discover._looks_like_feed(b'<?xml version="1.0"?><rss>') is True
    assert discover._looks_like_feed(b"<rss version='2.0'>") is True
    assert discover._looks_like_feed(b'<feed xmlns="...">') is True
    assert discover._looks_like_feed(
        b'{"version":"https://jsonfeed.org/version/1.1"}'
    ) is True
    # Leading whitespace is tolerated.
    assert discover._looks_like_feed(b"\n\n   <?xml version='1.0'?>") is True
    # Case-insensitive on the markup.
    assert discover._looks_like_feed(b"<RSS VERSION='2.0'>") is True
    # HTML is not a feed.
    assert discover._looks_like_feed(NOT_FEED_HTML) is False
    assert discover._looks_like_feed(b"<html><body>hi</body></html>") is False
    assert discover._looks_like_feed(b"") is False
