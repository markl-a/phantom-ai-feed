from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SHARED_LINK = "https://example.com/shared-breakthrough"


def _rss(title_link_pairs):
    items = "".join(
        f"<item><title>{t}</title><link>{link}</link>"
        f"<description>{t} details.</description></item>"
        for t, link in title_link_pairs
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<rss version='2.0'><channel><title>c</title>{items}</channel></rss>"
    )


def _write_feeds(tmp_path: Path) -> Path:
    research = tmp_path / "research.xml"
    research.write_text(
        _rss(
            [
                ("Shared Breakthrough Model", SHARED_LINK),
                ("Niche research note", "https://example.com/niche"),
            ]
        ),
        encoding="utf-8",
    )
    community = tmp_path / "community.xml"
    community.write_text(
        _rss([("Shared Breakthrough Model", SHARED_LINK)]),
        encoding="utf-8",
    )
    toml = tmp_path / "feeds.toml"
    toml.write_text(
        "[[feed]]\n"
        'name = "arxiv-feed"\n'
        f'url = "{research.as_uri()}"\n'
        'category = "research"\n\n'
        "[[feed]]\n"
        'name = "hn-feed"\n'
        f'url = "{community.as_uri()}"\n'
        'category = "community"\n',
        encoding="utf-8",
    )
    return toml


def _run_pipeline(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "phantom_ai_feed.pipeline", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )


def test_pipeline_runs_all_stages_in_one_invocation(tmp_path):
    base = tmp_path / "base"
    toml = _write_feeds(tmp_path)
    today = datetime.date.today().isoformat()

    proc = _run_pipeline(
        "--weekly",
        "--use-stub",
        "--force",
        "--feeds",
        str(toml),
        "--base-dir",
        str(base),
        "--date",
        today,
    )

    assert proc.returncode == 0, proc.stderr
    assert (base / f"{today}.md").exists()
    assert (base / f"weekly-questions-{today}.md").exists()

    store = base / "srs.jsonl"
    assert store.exists()
    cards = [
        json.loads(line)
        for line in store.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(cards) >= 1

    assert (base / f"weekly-{today}.md").exists()
    assert (base / f"newsletter-draft-{today}.md").exists()


def test_pipeline_stops_when_first_stage_input_empty(tmp_path):
    base = tmp_path / "base"
    empty_toml = tmp_path / "empty.toml"
    empty_toml.write_text("# no feeds\n", encoding="utf-8")
    today = datetime.date.today().isoformat()

    proc = _run_pipeline(
        "--weekly",
        "--use-stub",
        "--force",
        "--feeds",
        str(empty_toml),
        "--base-dir",
        str(base),
        "--date",
        today,
    )

    assert proc.returncode != 0
    assert not (base / f"weekly-questions-{today}.md").exists()
    assert not (base / "srs.jsonl").exists()
    assert "pipeline" in proc.stderr.lower()
