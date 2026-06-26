"""Packaging regression tests for the public CLI surface."""
from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def test_pyproject_declares_installable_console_scripts():
    assert PYPROJECT.exists(), "phantom-ai-feed must be installable with pip -e ."
    with PYPROJECT.open("rb") as fp:
        data = tomllib.load(fp)

    scripts = data["project"]["scripts"]
    expected = {
        "phantom-ai-feed": "phantom_ai_feed.pipeline:main",
        "phantom-ai-feed-digest": "phantom_ai_feed.digest:main",
        "phantom-ai-feed-weekly": "phantom_ai_feed.weekly:main",
        "phantom-ai-feed-recall": "phantom_ai_feed.recall:main",
        "phantom-ai-feed-srs": "phantom_ai_feed.srs:main",
        "phantom-ai-feed-export": "phantom_ai_feed.source_export:main",
        "phantom-ai-feed-scenario": "phantom_ai_feed.knowledge_scenario:main",
    }
    assert scripts == expected


def test_console_script_targets_are_importable_and_callable():
    with PYPROJECT.open("rb") as fp:
        scripts = tomllib.load(fp)["project"]["scripts"]

    for target in scripts.values():
        module_name, _, attr = target.partition(":")
        module = importlib.import_module(module_name)
        entry = getattr(module, attr)
        assert callable(entry), target
