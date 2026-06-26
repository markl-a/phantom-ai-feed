from __future__ import annotations

import json
from pathlib import Path

from phantom_ai_feed import demo_loop, source_export


def test_source_export_demo_writes_adapter_collection_and_review_bundle(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "knowledge-loop"
    out = tmp_path / "source-export"

    assert demo_loop.main(["--out", str(source), "--date", "2026-06-26", "--query", "RAG"]) == 0
    capsys.readouterr()

    assert source_export.main(["--source", str(source), "--out", str(out)]) == 0
    manifest_path = Path(capsys.readouterr().out.strip())
    assert manifest_path == out / "manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    adapter = json.loads((out / "source-adapter-contract.json").read_text(encoding="utf-8"))
    collection = json.loads((out / "collection-export.json").read_text(encoding="utf-8"))
    review = json.loads((out / "review-export.json").read_text(encoding="utf-8"))
    summary = (out / "summary.md").read_text(encoding="utf-8")

    assert manifest["schema_version"] == 1
    assert manifest["mode"] == "synthetic_source_export_bundle"
    assert manifest["source_mode"] == "synthetic_knowledge_intake_loop"
    assert manifest["data_policy"] == "synthetic_only"
    assert manifest["private_data_included"] is False
    assert manifest["external_network"] is False
    assert manifest["llm_provider"] == "stub_or_disabled"
    assert manifest["live_sources_required"] is False
    assert manifest["artifacts"] == {
        "adapter_contract": "source-adapter-contract.json",
        "collection_export": "collection-export.json",
        "review_export": "review-export.json",
        "summary": "summary.md",
    }

    assert adapter["mode"] == "source_adapter_contract"
    assert adapter["required_fields"] == [
        "source_id",
        "source_type",
        "fetch_policy",
        "license_note",
        "citation_policy",
        "output_schema",
    ]
    assert adapter["source_types"] == ["fixture", "rss", "web_page", "newsletter_export", "paper_metadata"]
    assert adapter["default_live_fetch"] == "disabled"

    assert collection["mode"] == "synthetic_collection_export"
    assert collection["query"] == "RAG"
    assert collection["source_count"] == 4
    assert collection["item_count"] == 4
    assert [item["title"] for item in collection["items"][:2]] == [
        "Synthetic RAG evaluation harness",
        "Synthetic retrieval grounding checklist",
    ]
    assert all(item["source_policy"] == "synthetic_fixture" for item in collection["items"])
    assert all("content_hash" in item for item in collection["items"])

    assert review["mode"] == "synthetic_review_export"
    assert review["card_count"] == 4
    assert review["due_count"] == 4
    assert review["cards"][0]["question_id"] == "2026-06-26-q1"
    assert review["cards"][0]["source_title"] == "Synthetic RAG evaluation harness"

    exported_text = "\n".join(
        path.read_text(encoding="utf-8") for path in out.iterdir() if path.is_file()
    )
    forbidden = (
        "private reading",
        "api key",
        "credential",
        "cookie",
        "personal annotation",
        "live source fetch",
    )
    assert all(term not in exported_text.lower() for term in forbidden)
    assert "Source export bundle" in summary


def test_source_export_demo_rejects_private_or_network_source_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "bad-source"
    source.mkdir()
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "mode": "synthetic_knowledge_intake_loop",
                "data_policy": "synthetic_only",
                "private_data_included": False,
                "external_network": True,
                "llm_provider": "stub_or_disabled",
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )

    rc = source_export.main(["--source", str(source), "--out", str(tmp_path / "out")])

    assert rc == 1
    assert "only accepts safe synthetic demo-loop bundles" in capsys.readouterr().err


def test_source_export_demo_rejects_artifact_paths_outside_bundle(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "knowledge-loop"

    assert demo_loop.main(["--out", str(source), "--date", "2026-06-26", "--query", "RAG"]) == 0
    capsys.readouterr()
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["source_items"] = "../outside-source-items.jsonl"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    rc = source_export.main(["--source", str(source), "--out", str(tmp_path / "out")])

    assert rc == 1
    assert "artifact paths must stay inside the bundle" in capsys.readouterr().err


def test_source_export_demo_is_byte_stable_for_same_inputs(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "knowledge-loop"
    a = tmp_path / "a"
    b = tmp_path / "b"

    assert demo_loop.main(["--out", str(source), "--date", "2026-06-26", "--query", "RAG"]) == 0
    capsys.readouterr()

    assert source_export.main(["--source", str(source), "--out", str(a)]) == 0
    capsys.readouterr()
    assert source_export.main(["--source", str(source), "--out", str(b)]) == 0
    capsys.readouterr()

    for rel in (
        "manifest.json",
        "source-adapter-contract.json",
        "collection-export.json",
        "review-export.json",
        "summary.md",
    ):
        assert (a / rel).read_text(encoding="utf-8") == (b / rel).read_text(
            encoding="utf-8"
        )
