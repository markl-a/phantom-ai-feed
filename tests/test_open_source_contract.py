from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_readme_documents_synthetic_knowledge_loop() -> None:
    text = _read("README.md")

    assert "demo-loop" in text
    assert "source_export" in text
    assert "knowledge_scenario" in text
    assert "docs/SYNTHETIC_KNOWLEDGE_LOOP.md" in text
    assert "docs/SOURCE_EXPORT_BUNDLE.md" in text
    assert "docs/KNOWLEDGE_SCENARIO_BUNDLE.md" in text
    assert "synthetic" in text.lower()
    assert "no network" in text.lower() or "no-network" in text.lower()
    assert "private reading" in text.lower()


def test_synthetic_knowledge_loop_contract_documents_manifest_and_artifacts() -> None:
    text = _read("docs/SYNTHETIC_KNOWLEDGE_LOOP.md")

    assert "demo-loop" in text
    assert "manifest.json" in text
    assert "synthetic_knowledge_intake_loop" in text
    assert "synthetic_only" in text
    assert "private_data_included" in text
    assert "external_network" in text
    assert "stub_or_disabled" in text
    for artifact in (
        "source-items.jsonl",
        "digest.md",
        "aifeed.db",
        "recall-results.json",
        "review-cards.json",
        "srs.jsonl",
        "srs-due-YYYY-MM-DD.md",
        "summary.md",
    ):
        assert artifact in text


def test_source_export_contract_documents_adapter_collection_and_review_bundle() -> None:
    text = _read("docs/SOURCE_EXPORT_BUNDLE.md")

    assert "source_export" in text
    assert "manifest.json" in text
    assert "source-adapter-contract.json" in text
    assert "collection-export.json" in text
    assert "review-export.json" in text
    assert "synthetic_source_export_bundle" in text
    assert "synthetic_only" in text
    assert "private_data_included=false" in text
    assert "external_network=false" in text
    assert "stub_or_disabled" in text
    assert "live_sources_required" in text
    assert "source_id" in text
    assert "citation_policy" in text
    assert "byte-stable" in text


def test_knowledge_scenario_contract_documents_p3_recall_srs_bundle() -> None:
    text = _read("docs/KNOWLEDGE_SCENARIO_BUNDLE.md")

    assert "knowledge_scenario" in text
    assert "manifest.json" in text
    assert "knowledge-scenario.json" in text
    assert "recall-review-plan.json" in text
    assert "synthetic_knowledge_scenario_bundle" in text
    assert "synthetic_only" in text
    assert "private_data_included=false" in text
    assert "external_network=false" in text
    assert "stub_or_disabled" in text
    assert "live_sources_required" in text
    assert "full_question_included=false" in text
    assert "raw_source_excerpt_included=false" in text
    assert "byte-stable" in text
