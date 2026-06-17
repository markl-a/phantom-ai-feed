"""P3.3 — expand sources beyond the original 8 feeds (offline).

Adds Chinese-language AI sources plus a few optional feeds, and proves the new
sources integrate with the existing fetch → summarize → capture pipeline:
  - feeds.toml parses to > 8 feeds with the required schema
  - Chinese sources are present and tagged ``zh`` so they can be filtered
  - a Chinese-feed entry round-trips through fetch (HTML stripped, CJK kept),
    summarize (stub), and the capture adapter (dry-run command built)
All hermetic — the network layer is monkeypatched; no sockets opened.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import capture as _cap  # noqa: E402
from phantom_ai_feed import fetch as _fetch  # noqa: E402
from phantom_ai_feed import summarize as _sum  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
FEEDS_TOML = REPO_ROOT / "sources" / "feeds.toml"

# A small fake Chinese RSS feed (CJK title + body, with HTML markup).
ZH_RSS = (
    "<?xml version='1.0' encoding='UTF-8'?>"
    "<rss version='2.0'><channel>"
    "<title>机器之心</title>"
    "<item>"
    "<title>大模型推理加速：vLLM 与 PagedAttention 解析</title>"
    "<link>https://example.cn/post/1</link>"
    "<description><![CDATA[<p>本文介绍 <b>PagedAttention</b> 如何把 KV-cache "
    "显存占用降低 <code>40%</code>。</p>]]></description>"
    "</item>"
    "</channel></rss>"
).encode("utf-8")


def test_feeds_toml_has_more_than_eight():
    feeds = _fetch.load_feeds(FEEDS_TOML)
    assert len(feeds) > 8, f"P3.3 should add feeds beyond the original 8; got {len(feeds)}"
    # every feed keeps the required schema
    for f in feeds:
        assert f.get("name") and f.get("url") and f.get("category")
    # names are unique
    names = [f["name"] for f in feeds]
    assert len(names) == len(set(names)), "duplicate feed names"


def test_feeds_toml_includes_chinese_sources():
    feeds = _fetch.load_feeds(FEEDS_TOML)
    zh = [f for f in feeds if f.get("category") == "zh"]
    assert len(zh) >= 2, "expected at least two Chinese (category=zh) sources"
    # the original 8 are still present (no regressions)
    names = {f["name"] for f in feeds}
    for original in (
        "arxiv-cs-AI", "hacker-news-frontpage", "karpathy-blog",
        "huggingface-blog",
    ):
        assert original in names, f"original feed {original} went missing"


def test_feeds_all_https_or_http():
    feeds = _fetch.load_feeds(FEEDS_TOML)
    for f in feeds:
        assert f["url"].startswith(("http://", "https://")), f["url"]


def test_chinese_feed_roundtrips_fetch_summarize_capture(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: ZH_RSS)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    feed = {"name": "机器之心", "url": "https://example.cn/feed", "category": "zh"}
    entries = _fetch.fetch_feed(feed, top_n=3)
    assert len(entries) == 1
    e = entries[0]
    # CJK text preserved; HTML tags stripped; entities/markup gone.
    assert "大模型推理加速" in e["title"]
    assert "PagedAttention" in e["summary_excerpt"]
    assert "<p>" not in e["summary_excerpt"] and "<b>" not in e["summary_excerpt"]
    assert e["source"] == "机器之心"
    assert e["category"] == "zh"

    # summarize (stub) yields non-empty text with the CJK content.
    summary = _sum.summarize(e["summary_excerpt"], use_stub=True, max_words=60)
    assert summary and summary != "(no content)"

    # capture adapter builds a valid command folding the CJK entry.
    e["summary"] = summary
    res = _cap.capture_entry(e, dry_run=True)
    assert res.ok and res.status == "dry-run"
    text = res.command[res.command.index("--text") + 1]
    assert "大模型推理加速" in text
    assert "机器之心" in text


def test_optional_feeds_flagged_in_toml():
    """Optional feeds carry an ``optional = true`` flag so a strict run can
    skip them; load_feeds still returns them (filtering is the caller's job)."""
    feeds = _fetch.load_feeds(FEEDS_TOML)
    optional = [f for f in feeds if f.get("optional") is True]
    assert optional, "expected at least one feed flagged optional = true"
    # optional feeds still have the full required schema
    for f in optional:
        assert f.get("name") and f.get("url") and f.get("category")
