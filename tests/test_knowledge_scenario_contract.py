from __future__ import annotations

import json
from pathlib import Path

from phantom_ai_feed import demo_loop, knowledge_scenario


def test_knowledge_scenario_writes_recall_srs_proof_bundle(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "knowledge-loop"
    out = tmp_path / "scenario"

    assert demo_loop.main(["--out", str(source), "--date", "2026-06-26", "--query", "RAG"]) == 0
    capsys.readouterr()

    assert knowledge_scenario.main(["--source", str(source), "--out", str(out)]) == 0
    manifest_path = Path(capsys.readouterr().out.strip())
    assert manifest_path == out / "manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenario = json.loads((out / "knowledge-scenario.json").read_text(encoding="utf-8"))
    review_plan = json.loads((out / "recall-review-plan.json").read_text(encoding="utf-8"))
    summary = (out / "summary.md").read_text(encoding="utf-8")

    assert manifest["schema_version"] == 1
    assert manifest["mode"] == "synthetic_knowledge_scenario_bundle"
    assert manifest["source_mode"] == "synthetic_knowledge_intake_loop"
    assert manifest["data_policy"] == "synthetic_only"
    assert manifest["private_data_included"] is False
    assert manifest["external_network"] is False
    assert manifest["llm_provider"] == "stub_or_disabled"
    assert manifest["live_sources_required"] is False
    assert manifest["artifacts"] == {
        "review_plan": "recall-review-plan.json",
        "scenario": "knowledge-scenario.json",
        "summary": "summary.md",
    }

    assert scenario["mode"] == "synthetic_recall_srs_scenario"
    assert scenario["query"] == "RAG"
    assert scenario["coverage"] == {
        "source_count": 4,
        "item_count": 4,
        "captured_entries": 4,
        "recall_hits": 2,
        "review_cards": 4,
        "due_cards": 4,
    }
    assert scenario["recall"]["top_hit"]["title"] == "Synthetic RAG evaluation harness"
    assert scenario["recall"]["top_hit"]["source"] == "synthetic-research"
    assert scenario["recall"]["raw_excerpt_included"] is False
    assert scenario["review_readiness"]["cards_ready"] == 4
    assert scenario["review_readiness"]["due_cards_ready"] == 4
    assert scenario["review_readiness"]["first_due_card_id"] == "2026-06-26-q1"
    assert scenario["readiness"] == {
        "multi_source_intake_ready": True,
        "recall_grounded_in_store": True,
        "review_queue_ready": True,
        "scenario_shareable": True,
    }
    assert scenario["boundaries"]["live_source_fetch"] == "not_required"
    assert scenario["boundaries"]["cloud_llm"] == "not_required"
    assert scenario["boundaries"]["private_reading_history"] == "not_included"

    assert review_plan["mode"] == "synthetic_recall_review_plan"
    assert review_plan["query"] == "RAG"
    assert [item["question_id"] for item in review_plan["items"][:2]] == [
        "2026-06-26-q1",
        "2026-06-26-q2",
    ]
    assert all(item["full_question_included"] is False for item in review_plan["items"])
    assert "Knowledge scenario" in summary
    assert "RAG" in summary


def test_knowledge_scenario_is_byte_stable_and_excludes_private_payloads(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "knowledge-loop"
    a = tmp_path / "a"
    b = tmp_path / "b"

    assert demo_loop.main(["--out", str(source), "--date", "2026-06-26", "--query", "RAG"]) == 0
    capsys.readouterr()

    private_note = "PRIVATE_READING_NOTE_DO_NOT_EXPORT_02b8"
    (source / "artifacts" / "private-reading.md").write_text(
        f"# {private_note}\napi key\ncookie\n",
        encoding="utf-8",
    )

    assert knowledge_scenario.main(["--source", str(source), "--out", str(a)]) == 0
    capsys.readouterr()
    assert knowledge_scenario.main(["--source", str(source), "--out", str(b)]) == 0
    capsys.readouterr()

    for rel in ("manifest.json", "knowledge-scenario.json", "recall-review-plan.json", "summary.md"):
        assert (a / rel).read_text(encoding="utf-8") == (b / rel).read_text(
            encoding="utf-8"
        )

    exported_text = "\n".join(
        path.read_text(encoding="utf-8") for path in a.iterdir() if path.is_file()
    )
    forbidden = (
        private_note,
        "api key",
        "cookie",
        "local evaluation harness compares retrieved context",
        "explain the key engineering risk",
        "private-reading.md",
        "personal annotation",
        "live source fetch",
    )
    assert all(term.lower() not in exported_text.lower() for term in forbidden)


def test_knowledge_scenario_rejects_source_artifact_paths_outside_bundle(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "knowledge-loop"

    assert demo_loop.main(["--out", str(source), "--date", "2026-06-26", "--query", "RAG"]) == 0
    capsys.readouterr()
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["recall_results"] = "../outside-recall.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    rc = knowledge_scenario.main(["--source", str(source), "--out", str(tmp_path / "out")])

    assert rc == 1
    assert "artifact paths must stay inside the bundle" in capsys.readouterr().err
