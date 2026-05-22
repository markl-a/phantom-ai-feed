"""Live network test against Hacker News RSS — small, fast, public.

Marked to skip when offline (`PHANTOM_AI_FEED_OFFLINE=1`).
"""
from __future__ import annotations

import os
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed.fetch import fetch_feed, load_feeds  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent
FEEDS_TOML = REPO_ROOT / "sources" / "feeds.toml"


def test_load_feeds_parses_8_entries():
    feeds = load_feeds(FEEDS_TOML)
    assert len(feeds) >= 8
    names = {f["name"] for f in feeds}
    assert "hacker-news-frontpage" in names


@pytest.mark.skipif(
    os.environ.get("PHANTOM_AI_FEED_OFFLINE") == "1",
    reason="offline mode",
)
def test_fetch_hn_returns_three_entries():
    feeds = load_feeds(FEEDS_TOML)
    hn = next(f for f in feeds if f["name"] == "hacker-news-frontpage")
    try:
        entries = fetch_feed(hn, top_n=3)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        pytest.skip(f"network unavailable: {e}")
    assert len(entries) >= 3
    e0 = entries[0]
    assert e0["title"]
    assert e0["link"].startswith("http")
    assert e0["source"] == "hacker-news-frontpage"
    assert e0["category"] == "community"
