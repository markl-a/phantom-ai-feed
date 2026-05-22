"""RSS/Atom fetcher — stdlib only.

Refactored from hailmary/phantom-ai-feed/scripts/heartbeat-daily.py.
Exposes a library API instead of writing files directly so digest.py
can compose fetch → summarize → write.
"""
from __future__ import annotations

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

TIMEOUT_S = 15
TOP_N_DEFAULT = 3
UA = "phantom-ai-feed/0.1 (+https://github.com/markl-a/phantom-ai-feed)"
_NS = {"atom": "http://www.w3.org/2005/Atom"}


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


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.read()


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return " ".join(el.text.split())


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
            "title": _text(item.find("title")),
            "link": link,
            "summary_excerpt": _text(item.find("description"))[:400],
        })
    # Atom
    if not items:
        for entry in root.findall("atom:entry", _NS):
            link_el = entry.find("atom:link", _NS)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = (
                _text(entry.find("atom:summary", _NS))
                or _text(entry.find("atom:content", _NS))
            )
            items.append({
                "title": _text(entry.find("atom:title", _NS)),
                "link": link,
                "summary_excerpt": summary[:400],
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
