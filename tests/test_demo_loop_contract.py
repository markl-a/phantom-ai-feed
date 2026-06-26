from __future__ import annotations

import json
from pathlib import Path

from phantom_ai_feed import demo_loop, store


def test_demo_loop_writes_synthetic_knowledge_intake_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    out = tmp_path / "bundle"

    rc = demo_loop.main(
        [
            "--out",
            str(out),
            "--date",
            "2026-06-26",
            "--query",
            "RAG",
        ]
    )

    assert rc == 0
    manifest_path = Path(capsys.readouterr().out.strip())
    assert manifest_path == out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["mode"] == "synthetic_knowledge_intake_loop"
    assert manifest["date"] == "2026-06-26"
    assert manifest["query"] == "RAG"
    assert manifest["data_policy"] == "synthetic_only"
    assert manifest["private_data_included"] is False
    assert manifest["external_network"] is False
    assert manifest["llm_provider"] == "stub_or_disabled"
    assert manifest["counts"] == {
        "source_items": 4,
        "captured_entries": 4,
        "recall_hits": 2,
        "review_cards": 4,
        "due_cards": 4,
    }

    expected = {
        "source_items",
        "digest",
        "fts_db",
        "recall_results",
        "review_cards",
        "srs_store",
        "srs_due",
        "summary",
    }
    assert set(manifest["artifacts"]) == expected
    for rel in manifest["artifacts"].values():
        assert (out / rel).exists()

    recall = json.loads(
        (out / manifest["artifacts"]["recall_results"]).read_text(encoding="utf-8")
    )
    assert [row["title"] for row in recall] == [
        "Synthetic RAG evaluation harness",
        "Synthetic retrieval grounding checklist",
    ]

    digest = (out / manifest["artifacts"]["digest"]).read_text(encoding="utf-8")
    assert "Synthetic AI feed digest" in digest
    assert "Synthetic RAG evaluation harness" in digest
    assert "private" not in digest.lower()
    assert "api key" not in digest.lower()

    rows = store.recall("RAG", db_path=out / manifest["artifacts"]["fts_db"], limit=5)
    assert len(rows) == 2
    review = (out / manifest["artifacts"]["srs_due"]).read_text(encoding="utf-8")
    assert "4 cards" in review


def test_demo_loop_is_stable_for_same_inputs_except_sqlite_bytes(
    tmp_path: Path,
    capsys,
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    args = ["--date", "2026-06-26", "--query", "RAG"]

    assert demo_loop.main([*args, "--out", str(a)]) == 0
    capsys.readouterr()
    assert demo_loop.main([*args, "--out", str(b)]) == 0
    capsys.readouterr()

    rels = (
        "manifest.json",
        "artifacts/source-items.jsonl",
        "artifacts/digest.md",
        "artifacts/recall-results.json",
        "artifacts/review-cards.json",
        "artifacts/srs.jsonl",
        "artifacts/srs-due-2026-06-26.md",
        "artifacts/summary.md",
    )
    for rel in rels:
        assert (a / rel).read_text(encoding="utf-8") == (b / rel).read_text(
            encoding="utf-8"
        )


def test_demo_loop_reusing_output_directory_is_idempotent(tmp_path: Path, capsys) -> None:
    out = tmp_path / "bundle"
    args = ["--out", str(out), "--date", "2026-06-26", "--query", "RAG"]

    assert demo_loop.main(args) == 0
    capsys.readouterr()
    first_manifest = (out / "manifest.json").read_text(encoding="utf-8")
    first_srs = (out / "artifacts" / "srs.jsonl").read_text(encoding="utf-8")

    assert demo_loop.main(args) == 0
    capsys.readouterr()

    assert (out / "manifest.json").read_text(encoding="utf-8") == first_manifest
    assert (out / "artifacts" / "srs.jsonl").read_text(encoding="utf-8") == first_srs
