from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_POLICY = REPO_ROOT / "docs" / "SOURCE_POLICY.md"
FEEDS_TOML = REPO_ROOT / "sources" / "feeds.toml"


def test_source_policy_documents_public_registry_contract():
    text = SOURCE_POLICY.read_text(encoding="utf-8")

    assert "sources/feeds.toml" in text
    assert "optional = true" in text
    assert "--strict" in text
    assert "PHANTOM_AI_FEED_OFFLINE=1" in text
    assert "private credentials" in text
    assert "Closed platforms" in text


def test_source_policy_matches_current_registry_semantics():
    registry = FEEDS_TOML.read_text(encoding="utf-8")
    policy = SOURCE_POLICY.read_text(encoding="utf-8")

    assert "optional  = true" in registry or "optional = true" in registry
    assert "strict core" in policy
    assert "skip optional feeds" in policy
