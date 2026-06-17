"""Gap 4 — the `optional = true` feed flag must be consumable from the CLI.

feeds.toml flags some feeds ``optional = true`` and the suite asserts the flag
exists, explicitly noting "filtering is the caller's job" — but NO production
CLI path ever filtered on it. The flag was unit-tested data with zero runtime
behavior. Add a ``--strict`` flag to the digest + weekly CLIs that drops
optional feeds before fetching.

Proven END-TO-END via the real ``python -m phantom_ai_feed.digest`` CLI run in
forced-offline mode (PHANTOM_AI_FEED_OFFLINE=1, no sockets): every feed renders
as a section, so ``--strict`` is observable as the optional feed's section
being absent while the core feed's remains.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_feeds(tmp_path: Path) -> Path:
    toml = tmp_path / "feeds.toml"
    toml.write_text(
        "[[feed]]\n"
        'name = "core-feed"\n'
        'url = "https://example.com/core.xml"\n'
        'category = "research"\n\n'
        "[[feed]]\n"
        'name = "optional-feed"\n'
        'url = "https://example.com/optional.xml"\n'
        'category = "blog"\n'
        "optional = true\n",
        encoding="utf-8",
    )
    return toml


def _run(tmp_path: Path, *extra: str) -> str:
    toml = _write_feeds(tmp_path)
    out_dir = tmp_path / ("out" + "".join(extra))
    env = dict(os.environ, PHANTOM_AI_FEED_OFFLINE="1")
    proc = subprocess.run(
        [sys.executable, "-m", "phantom_ai_feed.digest",
         "--feeds", str(toml), "--out", str(out_dir),
         "--use-stub", "--force", *extra],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(REPO_ROOT), env=env,
    )
    assert proc.returncode == 0, proc.stderr
    md = list(out_dir.glob("20*.md"))
    assert md, f"no digest written; stderr={proc.stderr}"
    return md[0].read_text(encoding="utf-8")


def test_strict_skips_optional_feeds(tmp_path):
    body = _run(tmp_path, "--strict")
    assert "core-feed" in body, "core feed must still be present under --strict"
    assert "optional-feed" not in body, "optional feed must be skipped under --strict"


def test_without_strict_optional_feeds_kept(tmp_path):
    # Control: default run keeps the optional feed (backward compatible).
    body = _run(tmp_path)
    assert "core-feed" in body
    assert "optional-feed" in body
