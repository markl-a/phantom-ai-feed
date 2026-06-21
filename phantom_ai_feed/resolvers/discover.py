"""Generic website RSS/Atom/JSON feed auto-discovery resolver — stdlib only.

Given a website URL, find its feed(s) by two means, in order:

1. **Head discovery.** Parse the page's ``<head>`` for the standard
   ``<link rel="alternate" type="application/rss+xml" href="...">`` advertisement
   (also atom+xml, json, feed+json). This is the authoritative, intended way for
   a site to declare its feed, so it wins when present.
2. **Path probing (fallback).** When the page advertises nothing, GET a short
   list of conventional feed paths (``/feed``, ``/rss.xml``, …) and keep any
   whose body *looks like* a feed. This is best-effort and per-candidate errors
   are swallowed (a 404 on ``/rss`` just means "not there", not a failure).

Network is reused from :mod:`phantom_ai_feed.fetch` so this inherits the shared
retry/backoff/User-Agent/offline behaviour — we never write our own urllib code.
"""
from __future__ import annotations

import argparse
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin

from phantom_ai_feed.resolvers import _net

# Feed MIME types we accept on a ``<link rel="alternate">`` (lower-cased compare).
_FEED_TYPES = frozenset({
    "application/rss+xml",
    "application/atom+xml",
    "application/json",
    "application/feed+json",
})

# Conventional feed paths, tried (in order) only when head discovery finds none.
_PROBE_PATHS = (
    "/feed",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/feed.xml",
    "/index.xml",
    "/feed/",
    "/?feed=rss2",
)

# How many leading bytes of a candidate body to sniff for feed-ness.
_SNIFF_BYTES = 512


class _FeedLinkParser(HTMLParser):
    """Collect ``href`` values of ``<link rel="alternate" type="<feed>">`` tags.

    ``rel`` and ``type`` are compared case-insensitively (the HTML spec treats
    both as ASCII-case-insensitive). Hrefs are collected in document order;
    de-duplication is left to the caller (which also resolves them against the
    base URL).
    """

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        # ``rel`` is a space-separated TOKEN LIST (HTML spec), so match when
        # "alternate" is ONE of the tokens — e.g. rel="alternate home".
        if "alternate" not in a.get("rel", "").lower().split():
            return
        if a.get("type", "").strip().lower() not in _FEED_TYPES:
            return
        href = a.get("href", "").strip()
        if href:
            self.hrefs.append(href)


def _dedup(seq: list[str]) -> list[str]:
    """Order-preserving de-duplication."""
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _looks_like_feed(body: bytes) -> bool:
    """True if ``body`` plausibly starts a feed document.

    Cheap structural sniff (no XML/JSON parse): strip a leading UTF-8 BOM and
    whitespace, lower the first ~512 bytes, and accept XML/RSS/Atom prologues or
    a body that actually LOOKS like JSON Feed. Good enough to reject HTML home
    pages returned by a probe.

    JSON Feed is only accepted when the body starts with ``{`` AND mentions
    ``jsonfeed.org`` — an HTML page that merely links to jsonfeed.org is not a
    feed. The BOM strip prevents a BOM-prefixed feed from being wrongly rejected
    (``bytes.lstrip()`` does NOT remove a leading ``\\xef\\xbb\\xbf``).
    """
    if not body:
        return False
    # Strip a leading UTF-8 BOM (lstrip() leaves it), then leading whitespace.
    sniff = body
    if sniff.startswith(b"\xef\xbb\xbf"):
        sniff = sniff[3:]
    head = sniff.lstrip()[:_SNIFF_BYTES].lower()
    if head.startswith((b"<?xml", b"<rss", b"<feed")):
        return True
    # JSON Feed: must actually be JSON (start with '{'), not just mention the URL.
    return head.startswith(b"{") and b"jsonfeed.org" in head


def discover_feeds(url: str) -> list[str]:
    """Discover feed URLs for a website ``url``.

    Returns an order-preserved, de-duplicated list of absolute feed URLs, or
    ``[]`` if none are found (including when the page itself cannot be fetched).
    """
    raw = _net.get_bytes(url)
    if raw is None:
        return []

    parser = _FeedLinkParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    if parser.hrefs:
        return _dedup([urljoin(url, href) for href in parser.hrefs])

    # Fallback: probe conventional paths, validate each body.
    found: list[str] = []
    for path in _PROBE_PATHS:
        candidate = urljoin(url, path)
        # Speculative probe: a single attempt (max_retries=0) so 8 candidates
        # can't amplify into dozens of requests via per-candidate backoff.
        body = _net.get_bytes(candidate, max_retries=0)
        if body is None:
            continue
        if _looks_like_feed(body):
            found.append(candidate)
    return _dedup(found)


def main(argv: list[str] | None = None) -> int:
    """CLI: print each discovered feed URL on its own line.

    Exits nonzero (with a stderr note) when nothing is discovered, so the
    command is usable in a shell pipeline / ``&&`` chain.
    """
    ap = argparse.ArgumentParser(
        prog="python -m phantom_ai_feed.resolvers.discover",
        description="Auto-discover RSS/Atom/JSON feeds for a website URL.",
    )
    ap.add_argument("url", help="website URL to inspect (e.g. https://example.com)")
    args = ap.parse_args(argv)

    feeds = discover_feeds(args.url)
    if not feeds:
        print(f"no feeds discovered for {args.url}", file=sys.stderr)
        return 1
    for f in feeds:
        print(f)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
