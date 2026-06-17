"""P1.2 — fetch/summarize reliability hardening (fully OFFLINE).

Covers three behaviours, all hermetic (the network layer ``_http_get`` is
monkeypatched; no sockets are opened):

1. Bounded retry/backoff on transient 429 / timeout, then success or give-up.
2. HTML stripping for feed bodies (tags removed, entities unescaped).
3. Per-feed status counts surfaced in the daily digest header.
"""
from __future__ import annotations

import datetime as _dt
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import digest as _digest  # noqa: E402
from phantom_ai_feed import fetch as _fetch  # noqa: E402

# --------------------------------------------------------------------------- #
# Fake RSS fixtures                                                           #
# --------------------------------------------------------------------------- #
RSS_WITH_HTML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Fake AI Feed</title>
  <item>
    <title>New &amp; faster transformer</title>
    <link>https://example.com/a</link>
    <description><![CDATA[<p>A <b>70B</b> model with <a href="x">38% less</a>
      KV-cache &amp; memory.</p>]]></description>
  </item>
  <item>
    <title>Second story</title>
    <link>https://example.com/b</link>
    <description>Latency &lt;100ms with Vec&lt;T&gt; &amp; a&lt;b math.</description>
  </item>
  <item>
    <title>Third story</title>
    <link>https://example.com/c</link>
    <description>Use the &lt;code&gt; tag inside &lt;p&gt; blocks.</description>
  </item>
</channel></rss>"""

RSS_OK = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><title>Hello</title><link>https://example.com/h</link>
    <description>world</description></item>
</channel></rss>"""


def _make_http429():
    return urllib.error.HTTPError(
        url="https://example.com", code=429, msg="Too Many Requests",
        hdrs=None, fp=None,
    )


# --------------------------------------------------------------------------- #
# 1. Bounded retry / backoff                                                  #
# --------------------------------------------------------------------------- #
def test_retry_succeeds_after_transient_429(monkeypatch):
    """Two 429s then a 200 → fetch_feed returns parsed entries; backoff is
    invoked twice and we never actually sleep."""
    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky_get(url):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _make_http429()
        return RSS_OK

    monkeypatch.setattr(_fetch, "_raw_http_get", flaky_get)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: sleeps.append(s))

    out = _fetch.fetch_feed(
        {"name": "x", "url": "https://example.com/feed"},
        top_n=3,
    )
    assert calls["n"] == 3        # 2 failures + 1 success
    assert len(sleeps) == 2       # backed off before each retry
    assert sleeps == sorted(sleeps)  # non-decreasing (exponential) backoff
    assert out and out[0]["title"] == "Hello"


def test_retry_gives_up_after_max_and_raises(monkeypatch):
    """Persistent 429 → raise after the bounded retry budget is exhausted."""
    calls = {"n": 0}

    def always_429(url):
        calls["n"] += 1
        raise _make_http429()

    monkeypatch.setattr(_fetch, "_raw_http_get", always_429)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    try:
        _fetch.fetch_feed({"name": "x", "url": "https://e/f"}, top_n=3)
    except urllib.error.HTTPError as e:
        assert e.code == 429
    else:
        raise AssertionError("expected HTTPError after exhausting retries")

    # default budget = MAX_RETRIES + 1 total attempts
    assert calls["n"] == _fetch.MAX_RETRIES + 1


def test_retry_on_timeout_then_success(monkeypatch):
    """A TimeoutError is also retried (transient), not raised immediately."""
    calls = {"n": 0}
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    def flaky(url):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("read timed out")
        return RSS_OK

    monkeypatch.setattr(_fetch, "_raw_http_get", flaky)
    out = _fetch.fetch_feed({"name": "x", "url": "https://e/f"}, top_n=1)
    assert calls["n"] == 2
    assert out[0]["title"] == "Hello"


def test_non_retryable_http_error_raises_immediately(monkeypatch):
    """A 404 (client error, not 429) must NOT be retried — fail fast."""
    calls = {"n": 0}

    def get_404(url):
        calls["n"] += 1
        raise urllib.error.HTTPError(
            url="u", code=404, msg="Not Found", hdrs=None, fp=None
        )

    monkeypatch.setattr(_fetch, "_raw_http_get", get_404)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    try:
        _fetch.fetch_feed({"name": "x", "url": "https://e/f"}, top_n=1)
    except urllib.error.HTTPError as e:
        assert e.code == 404
    else:
        raise AssertionError("expected 404 to propagate")
    assert calls["n"] == 1  # no retries


# --------------------------------------------------------------------------- #
# 2. HTML stripping                                                           #
# --------------------------------------------------------------------------- #
def test_html_is_stripped_from_excerpts(monkeypatch):
    monkeypatch.setattr(_fetch, "_raw_http_get", lambda url: RSS_WITH_HTML)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)

    out = _fetch.fetch_feed({"name": "fake", "url": "https://e/f"}, top_n=3)
    assert len(out) == 3
    ex0 = out[0]["summary_excerpt"]
    # No tags survive.
    assert "<" not in ex0 and ">" not in ex0
    assert "<p>" not in ex0 and "<b>" not in ex0
    # Entities are unescaped, text content preserved.
    assert "70B" in ex0
    assert "38% less" in ex0
    assert "KV-cache & memory" in ex0  # &amp; -> &

    # Second item: NON-tag-name angle expressions survive (the allowlist's real
    # value). ``<100ms``, ``Vec<T>``, ``a<b`` are kept because the char after
    # ``<`` is not a known HTML tag name.
    ex1 = out[1]["summary_excerpt"]
    assert ex1 == "Latency <100ms with Vec<T> & a<b math."

    # Third item: escaped prose that uses a real HTML tag NAME (&lt;code&gt;,
    # &lt;p&gt;) is INDISTINGUISHABLE from markup once ET decodes it, so it IS
    # stripped. This is the honest, documented behavior (see strip_html docstring
    # and the _HTML_TAGS note) — NOT a claim that all escaped prose survives.
    ex2 = out[2]["summary_excerpt"]
    assert ex2 == "Use the tag inside blocks."
    assert "<code>" not in ex2 and "<p>" not in ex2

    # Titles are also entity-decoded.
    assert out[0]["title"] == "New & faster transformer"


def test_strip_html_helper_collapses_whitespace():
    raw = "<p>Hello&nbsp; <b>world</b></p>\n\n  <i>again</i>"
    cleaned = _fetch.strip_html(raw)
    assert "<" not in cleaned
    assert cleaned == "Hello world again"


def test_strip_html_allowlisted_tag_name_prose_is_stripped():
    """ET-decoded input that uses a real HTML tag NAME is treated as markup and
    removed — the honest, documented limit. (Previously this case was masked by
    a test that only used the non-tag word ``<text>``.)

    ``strip_html`` is called with text as ElementTree's ``.text`` would yield it:
    XML entities ALREADY decoded, so ``&lt;code&gt;`` arrives as ``<code>`` —
    indistinguishable from genuine ``<code>`` markup.
    """
    # Allowlisted tag names -> stripped (cannot be told apart from markup).
    assert _fetch.strip_html("Use the <code> tag in <p> blocks.") == \
        "Use the tag in blocks."
    assert _fetch.strip_html("<time> and <table> words") == "and words"


def test_strip_html_non_tag_angle_expressions_survive():
    """The allowlist's genuine value: angle expressions whose first token is not
    a known tag name are preserved even after ET has decoded the entities."""
    assert _fetch.strip_html("if a < b and c > d") == "if a < b and c > d"
    assert _fetch.strip_html("latency <100ms target") == "latency <100ms target"
    assert _fetch.strip_html("Vec<T> in Rust") == "Vec<T> in Rust"


# --------------------------------------------------------------------------- #
# 3. Per-feed status counts in digest header                                  #
# --------------------------------------------------------------------------- #
def test_digest_header_has_per_feed_status_counts(monkeypatch, tmp_path):
    """One OK feed, one erroring feed, one empty feed → header reports the
    breakdown (ok / error / empty) and the OK count."""
    feeds = [
        {"name": "good", "url": "https://e/good", "category": "research"},
        {"name": "bad", "url": "https://e/bad", "category": "blog"},
        {"name": "empty", "url": "https://e/empty", "category": "misc"},
    ]
    monkeypatch.setattr(_digest._fetch, "load_feeds", lambda _p: feeds)

    EMPTY_RSS = b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'

    def fake_get(url):
        if url.endswith("/good"):
            return RSS_OK
        if url.endswith("/empty"):
            return EMPTY_RSS
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(_fetch, "_raw_http_get", fake_get)
    monkeypatch.setattr(_fetch.time, "sleep", lambda s: None)
    # Keep the test hermetic & fast: never shell out to a real `phantom` binary.
    monkeypatch.setattr(_digest, "_try_capture_fts5", lambda _e: None)

    out_dir = tmp_path / "out"
    out_path = _digest.run(
        feeds_toml=Path("ignored.toml"),
        out_dir=out_dir,
        use_stub=True,
        top_n=3,
        force=True,
    )
    text = out_path.read_text("utf-8")
    header = text.splitlines()
    joined = "\n".join(header[:8])

    # Per-feed status counts present in the header region.
    assert "1/3 feeds OK" in joined
    assert "error" in joined.lower()
    assert "empty" in joined.lower()
    # The single erroring feed is still rendered with its error downstream.
    assert "boom" in text
