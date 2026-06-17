"""Gap 1 — fetch must NOT eat real text after an inline HTML child element.

RSS/Atom bodies (and titles) in the wild routinely carry *well-formed* inline
HTML that is NOT wrapped in CDATA and NOT entity-escaped, e.g.

    <description>A <b>70B</b> model with <a href="x">38% less</a> memory.</description>

ElementTree parses ``<b>`` / ``<a>`` as CHILD elements, so reading only
``Element.text`` returns just ``"A "`` — every word after the first child
(``70B``, ``model with``, ``38% less``, ``memory``) is silently dropped. The
vision is explicit: "strips HTML to clean prose WITHOUT eating real text".

This is proven END-TO-END through the real ``python -m phantom_ai_feed.digest``
CLI: a ``file://`` feed is served from disk (no network, no monkeypatch), the
CLI writes its Markdown digest, and we assert the post-first-child text survives.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Inline HTML children (NOT CDATA, NOT escaped) in both title and description.
FEED_XML = (
    "<?xml version='1.0' encoding='UTF-8'?>"
    "<rss version='2.0'><channel><title>inline-feed</title>"
    "<item>"
    "<title>A <b>70B</b> model lands</title>"
    "<link>https://example.com/inline</link>"
    "<description>A <b>70B</b> model with <a href=\"x\">38% less</a> "
    "KV-cache memory and big wins.</description>"
    "</item>"
    "</channel></rss>"
)


def _write_feeds_toml(tmp_path: Path) -> Path:
    feed_xml = tmp_path / "inline.xml"
    feed_xml.write_text(FEED_XML, encoding="utf-8")
    toml = tmp_path / "feeds.toml"
    toml.write_text(
        "[[feed]]\n"
        'name = "inline-feed"\n'
        f'url = "{feed_xml.as_uri()}"\n'
        'category = "blog"\n',
        encoding="utf-8",
    )
    return toml


def test_digest_cli_preserves_text_after_inline_child(tmp_path):
    toml = _write_feeds_toml(tmp_path)
    out_dir = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "phantom_ai_feed.digest",
         "--feeds", str(toml), "--out", str(out_dir),
         "--use-stub", "--force"],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    md_files = list(out_dir.glob("*.md"))
    assert md_files, f"no digest written; stdout={proc.stdout} stderr={proc.stderr}"
    body = md_files[0].read_text(encoding="utf-8")

    # The whole story title survives — not just the leading "A".
    assert "70B" in body
    assert "model lands" in body
    # The body text AFTER the first inline child is preserved, not eaten.
    assert "38% less" in body
    assert "KV-cache memory and big wins" in body
    # And no raw tags leaked through.
    assert "<b>" not in body and "<a " not in body
