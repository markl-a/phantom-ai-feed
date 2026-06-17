"""RSS/Atom fetcher — stdlib only.

Refactored from hailmary/phantom-ai-feed/scripts/heartbeat-daily.py.
Exposes a library API instead of writing files directly so digest.py
can compose fetch → summarize → write.
"""
from __future__ import annotations

import html
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

TIMEOUT_S = 15
TOP_N_DEFAULT = 3
UA = "phantom-ai-feed/0.1 (+https://github.com/markl-a/phantom-ai-feed)"
_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Bounded retry/backoff for transient fetch failures (429 / timeouts / URLError).
# Total attempts = MAX_RETRIES + 1. Backoff is exponential: BACKOFF_BASE_S * 2**i.
MAX_RETRIES = 3
BACKOFF_BASE_S = 0.5
BACKOFF_CAP_S = 8.0

_WS_RE = re.compile(r"\s+")

# Common HTML/XHTML tags we strip from feed bodies. We restrict to an allowlist
# (rather than "anything between < and >") so that NON-tag angle expressions
# survive: ``a < b``, ``latency <100ms``, ``Vec<T>`` etc. are left intact because
# the word after ``<`` is not a known tag name.
#
# IMPORTANT (the un-fixable ambiguity): RSS/Atom feed bodies are HTML by
# convention (RSS <description> "may contain HTML"; Atom uses CDATA or
# type="html"). ElementTree's ``.text`` collapses BOTH real CDATA/entity markup
# AND author-escaped literal prose into the same decoded string — e.g. real
# ``<![CDATA[<code>x</code>]]>`` and escaped prose ``&lt;code&gt;`` both arrive
# here as the literal ``<code>``, with no marker of which was which. We therefore
# cannot reliably tell "was markup" from "was escaped prose" for an allowlisted
# tag NAME, and we resolve the tie toward the common case: treat it as markup and
# strip it. So escaped prose that happens to use a real HTML tag name (``<code>``,
# ``<p>``, …) IS removed; only non-tag-name angle expressions are preserved.
_HTML_TAGS = (
    "a|abbr|article|aside|b|blockquote|br|caption|cite|code|col|colgroup|dd|"
    "del|details|div|dl|dt|em|figcaption|figure|font|footer|h1|h2|h3|h4|h5|h6|"
    "header|hr|i|iframe|img|ins|kbd|li|main|mark|nav|ol|p|pre|q|s|samp|section|"
    "small|span|strong|sub|sup|table|tbody|td|tfoot|th|thead|time|tr|u|ul|wbr"
)
# Matches an opening/closing/self-closing tag for one of the known names, with
# optional attributes — e.g. <p>, </p>, <br/>, <a href="x">, <img src="y" />.
_TAG_RE = re.compile(
    rf"</?(?:{_HTML_TAGS})(?:\s[^<>]*?)?/?>",
    re.IGNORECASE,
)


def strip_html(raw: str) -> str:
    """Strip HTML markup and unescape entities from an HTML-format feed body,
    collapsing whitespace. Pure stdlib (regex + html.unescape) — feed bodies are
    short and well-formed enough that a full parser is overkill.

    Scope: RSS/Atom bodies are HTML by convention, so this removes HTML markup.
    Tags are matched against a known-HTML-tag allowlist, which preserves NON-tag
    angle expressions — ``a < b``, ``latency <100ms``, ``Vec<T>`` survive because
    the word after ``<`` is not a known tag name.

    It does NOT promise that arbitrary escaped prose survives. ElementTree
    decodes ``&lt;code&gt;`` to the literal ``<code>``, which is then
    indistinguishable from real ``<code>`` markup (e.g. from a CDATA body); such
    allowlisted tag-NAME words ARE stripped. This is the honest, irreducible
    limit of cleaning already-decoded text — see the ``_HTML_TAGS`` note above.

    Order matters: drop tags first, THEN unescape, so any entity inside the
    tag-stripped remainder (``&amp;`` → ``&``, ``&nbsp;`` → space) is resolved
    last.
    """
    if not raw:
        return ""
    no_tags = _TAG_RE.sub(" ", raw)
    unescaped = html.unescape(no_tags)
    return _WS_RE.sub(" ", unescaped).strip()


def _load_toml(path: Path) -> dict:
    """tomllib (3.11+) or tomli (3.10 fallback)."""
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:  # pragma: no cover - 3.10 path
        import tomli as tomllib  # type: ignore[no-redef]
    return tomllib.loads(path.read_text("utf-8"))


def load_feeds(toml_path: Path | str) -> list[dict]:
    """Return list of feed dicts: [{name, url, category}, ...]."""
    cfg = _load_toml(Path(toml_path))
    return list(cfg.get("feed", []))


def _raw_http_get(url: str) -> bytes:
    """The genuine single network fetch (no retries). Patched out in tests."""
    # PHANTOM_AI_FEED_OFFLINE=1 forces a genuine no-network mode: skip the fetch
    # immediately (fetch_all captures it per-feed) instead of hanging on timeouts.
    if os.environ.get("PHANTOM_AI_FEED_OFFLINE") == "1":
        raise urllib.error.URLError(
            "offline mode (PHANTOM_AI_FEED_OFFLINE=1): network fetch skipped"
        )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.read()


def _is_retryable(err: Exception) -> bool:
    """Transient failures worth retrying: HTTP 429, and timeouts. A plain
    URLError that wraps a timeout is also retryable; other client errors
    (e.g. 404) are not."""
    if isinstance(err, urllib.error.HTTPError):
        return err.code == 429 or 500 <= err.code < 600
    if isinstance(err, TimeoutError):
        return True
    if isinstance(err, urllib.error.URLError):
        # URLError.reason may itself be a TimeoutError/socket.timeout.
        return isinstance(err.reason, (TimeoutError, OSError))
    return False


def _http_get(url: str, *, max_retries: int = MAX_RETRIES) -> bytes:
    """Fetch ``url`` with bounded exponential backoff on transient errors
    (HTTP 429, 5xx, timeouts). Non-retryable errors (e.g. 404) propagate at
    once. After exhausting the budget, the last error is re-raised.

    ``time.sleep`` is called between attempts (monkeypatched to a no-op in
    tests so the suite stays fast and offline)."""
    last: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return _raw_http_get(url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            if attempt >= max_retries or not _is_retryable(e):
                raise
            delay = min(BACKOFF_BASE_S * (2 ** attempt), BACKOFF_CAP_S)
            time.sleep(delay)
    # Defensive: loop always returns or raises, but keep type-checkers happy.
    assert last is not None
    raise last


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return " ".join(el.text.split())


def _title(el: ET.Element | None) -> str:
    """Title text with HTML/entities normalised (titles can carry &amp; etc.)."""
    return strip_html(_text(el))


def _body(el: ET.Element | None, limit: int = 400) -> str:
    """Feed body (description / summary / content): strip HTML tags + unescape
    entities, then cap. ET decodes XML entities in plain text, but CDATA bodies
    arrive as raw HTML, so this is where tags/entities actually get cleaned."""
    return strip_html(_text(el))[:limit]


def _parse_entries(xml_bytes: bytes, top_n: int) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    items: list[dict] = []
    # RSS 2.0
    for item in root.findall(".//item"):
        link_el = item.find("link")
        link = _text(link_el) or (link_el.get("href", "") if link_el is not None else "")
        items.append({
            "title": _title(item.find("title")),
            "link": link,
            "summary_excerpt": _body(item.find("description")),
        })
    # Atom
    if not items:
        for entry in root.findall("atom:entry", _NS):
            link_el = entry.find("atom:link", _NS)
            link = link_el.get("href", "") if link_el is not None else ""
            summary_el = entry.find("atom:summary", _NS)
            content_el = entry.find("atom:content", _NS)
            summary = _body(summary_el) or _body(content_el)
            items.append({
                "title": _title(entry.find("atom:title", _NS)),
                "link": link,
                "summary_excerpt": summary,
            })
    return items[:top_n]


def fetch_feed(feed: dict, top_n: int = TOP_N_DEFAULT) -> list[dict]:
    """Fetch one feed dict. Returns [{title, link, summary_excerpt, source}, ...].

    Raises urllib.error.URLError / OSError / TimeoutError on network failure;
    caller decides whether to swallow.
    """
    raw = _http_get(feed["url"])
    out = _parse_entries(raw, top_n)
    for e in out:
        e["source"] = feed.get("name", feed.get("url", "unknown"))
        e["category"] = feed.get("category", "misc")
    return out


def fetch_all(
    feeds: Iterable[dict], top_n: int = TOP_N_DEFAULT
) -> list[tuple[dict, list[dict] | Exception]]:
    """Fetch every feed; per-feed error is captured (not raised)."""
    results: list[tuple[dict, list[dict] | Exception]] = []
    for f in feeds:
        try:
            results.append((f, fetch_feed(f, top_n)))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            results.append((f, e))
    return results
