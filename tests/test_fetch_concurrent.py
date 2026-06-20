"""fetch_all concurrency — feeds are fetched in parallel, not one-by-one.

Hermetic: the network layer ``_raw_http_get`` is monkeypatched; no sockets.
Concurrency is proven with a ``threading.Barrier`` — a sequential fetcher can
never get all N callers to the barrier at once, so it trips the timeout; only a
genuinely concurrent fetcher lets every feed reach the barrier together.
"""
from __future__ import annotations

import sys
import threading
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import fetch as _fetch  # noqa: E402

RSS_OK = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><title>Hello</title><link>https://example.com/h</link>
    <description>world</description></item>
</channel></rss>"""


def test_fetch_all_runs_feeds_concurrently(monkeypatch):
    """Three feeds must all reach a Barrier(3) at once → only possible if they
    are fetched concurrently. A sequential fetch trips the barrier timeout."""
    feeds = [
        {"name": "a", "url": "https://e/a"},
        {"name": "b", "url": "https://e/b"},
        {"name": "c", "url": "https://e/c"},
    ]
    barrier = threading.Barrier(len(feeds), timeout=3)

    def gated_get(url):
        barrier.wait()  # blocks until ALL feeds are in flight at once
        return RSS_OK

    monkeypatch.setattr(_fetch, "_raw_http_get", gated_get)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    out = _fetch.fetch_all(feeds, top_n=1)

    assert len(out) == 3
    for _feed, payload in out:
        assert isinstance(payload, list) and payload, payload
        assert payload[0]["title"] == "Hello"


def test_fetch_all_preserves_input_order(monkeypatch):
    """Concurrency must not scramble results: output order == input order, and
    each result is paired with the feed it belongs to."""
    feeds = [{"name": n, "url": f"https://e/{n}"} for n in ("alpha", "beta", "gamma")]

    def by_url(url):
        tail = url.rsplit("/", 1)[-1]
        return (
            b'<?xml version="1.0"?><rss version="2.0"><channel>'
            b"<item><title>" + tail.encode() + b"</title>"
            b"<link>https://e/" + tail.encode() + b"</link>"
            b"<description>x</description></item></channel></rss>"
        )

    monkeypatch.setattr(_fetch, "_raw_http_get", by_url)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    out = _fetch.fetch_all(feeds, top_n=1)

    assert [f["name"] for f, _ in out] == ["alpha", "beta", "gamma"]
    for feed, payload in out:
        assert payload[0]["title"] == feed["name"]


def test_fetch_all_captures_per_feed_error_concurrently(monkeypatch):
    """A single failing feed is captured as an Exception in its own slot; the
    other feeds still succeed (error isolation survives parallelisation)."""
    feeds = [
        {"name": "ok1", "url": "https://e/ok1"},
        {"name": "bad", "url": "https://e/bad"},
        {"name": "ok2", "url": "https://e/ok2"},
    ]

    def maybe_fail(url):
        if url.endswith("/bad"):
            raise urllib.error.URLError("boom")
        return RSS_OK

    monkeypatch.setattr(_fetch, "_raw_http_get", maybe_fail)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    out = _fetch.fetch_all(feeds, top_n=1)
    by_name = {f["name"]: payload for f, payload in out}

    assert isinstance(by_name["bad"], urllib.error.URLError)
    assert isinstance(by_name["ok1"], list) and by_name["ok1"]
    assert isinstance(by_name["ok2"], list) and by_name["ok2"]
