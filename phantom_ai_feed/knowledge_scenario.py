"""Synthetic knowledge-intake scenario proof artifacts.

This P3 bundle turns the P2 demo-loop output into a shareable proof that a
multi-source synthetic intake can be searched through the local recall store and
converted into an SRS review queue. It exports metadata-only evidence, not raw
source excerpts, full review questions, private reading notes, credentials, or
live-source claims.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def write_knowledge_scenario_bundle(
    *,
    source_bundle: str | Path,
    out_root: str | Path,
) -> Path:
    """Write a deterministic recall/SRS scenario bundle."""
    source = Path(source_bundle)
    out = Path(out_root)
    source_root, manifest = _load_source_manifest(source)
    _validate_source_manifest(manifest)

    artifacts = manifest.get("artifacts") or {}
    source_items = _load_jsonl_artifact(source_root, artifacts, "source_items")
    recall_results = _load_json_artifact(source_root, artifacts, "recall_results", default=[])
    review_cards = _load_json_artifact(source_root, artifacts, "review_cards", default=[])
    srs_records = _load_jsonl_artifact(source_root, artifacts, "srs_store")

    scenario = _build_scenario(
        manifest=manifest,
        source_items=source_items,
        recall_results=recall_results,
        review_cards=review_cards,
        srs_records=srs_records,
    )
    review_plan = _build_review_plan(
        manifest=manifest,
        source_items=source_items,
        review_cards=review_cards,
        srs_records=srs_records,
    )

    out.mkdir(parents=True, exist_ok=True)
    scenario_path = out / "knowledge-scenario.json"
    review_plan_path = out / "recall-review-plan.json"
    summary_path = out / "summary.md"
    scenario_path.write_text(_json(scenario), encoding="utf-8")
    review_plan_path.write_text(_json(review_plan), encoding="utf-8")
    summary_path.write_text(_summary(scenario), encoding="utf-8")

    out_manifest = {
        "schema_version": SCHEMA_VERSION,
        "mode": "synthetic_knowledge_scenario_bundle",
        "source_mode": manifest.get("mode", ""),
        "date": manifest.get("date", ""),
        "query": manifest.get("query", ""),
        "data_policy": "synthetic_only",
        "private_data_included": False,
        "external_network": False,
        "llm_provider": "stub_or_disabled",
        "live_sources_required": False,
        "artifacts": {
            "review_plan": _rel(out, review_plan_path),
            "scenario": _rel(out, scenario_path),
            "summary": _rel(out, summary_path),
        },
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(_json(out_manifest), encoding="utf-8")
    return manifest_path


def _load_source_manifest(source: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = source if source.is_file() else source / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("knowledge-scenario requires a demo-loop manifest.json")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("knowledge-scenario manifest must be a JSON object")
    return manifest_path.parent, raw


def _validate_source_manifest(manifest: dict[str, Any]) -> None:
    if (
        manifest.get("mode") != "synthetic_knowledge_intake_loop"
        or manifest.get("data_policy") != "synthetic_only"
        or manifest.get("private_data_included") is not False
        or manifest.get("external_network") is not False
        or manifest.get("llm_provider") != "stub_or_disabled"
    ):
        raise RuntimeError("knowledge-scenario only accepts safe synthetic demo-loop bundles")


def _load_json_artifact(
    source_root: Path,
    artifacts: dict[str, Any],
    key: str,
    *,
    default: Any,
) -> Any:
    rel = artifacts.get(key)
    if not isinstance(rel, str):
        return default
    path = _bundle_path(source_root, rel)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl_artifact(
    source_root: Path,
    artifacts: dict[str, Any],
    key: str,
) -> list[dict[str, Any]]:
    rel = artifacts.get(key)
    if not isinstance(rel, str):
        return []
    path = _bundle_path(source_root, rel)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _build_scenario(
    *,
    manifest: dict[str, Any],
    source_items: list[dict[str, Any]],
    recall_results: list[dict[str, Any]],
    review_cards: list[dict[str, Any]],
    srs_records: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = manifest.get("counts") or {}
    date = str(manifest.get("date") or "")
    due_records = _due_records(srs_records, date)
    source_count = len({str(item.get("source", "")) for item in source_items})
    top_hit = recall_results[0] if recall_results else {}
    matched_titles = [str(row.get("title", "")) for row in recall_results if isinstance(row, dict)]

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "synthetic_recall_srs_scenario",
        "source_mode": manifest.get("mode", ""),
        "date": date,
        "query": manifest.get("query", ""),
        "data_policy": {
            "synthetic_only": True,
            "private_data_included": False,
            "external_network": False,
            "llm_provider": "stub_or_disabled",
            "live_sources_required": False,
        },
        "coverage": {
            "source_count": source_count,
            "item_count": len(source_items),
            "captured_entries": int(counts.get("captured_entries") or len(source_items)),
            "recall_hits": len(recall_results),
            "review_cards": len(review_cards),
            "due_cards": len(due_records),
        },
        "recall": {
            "query": manifest.get("query", ""),
            "matched_titles": matched_titles,
            "top_hit": _safe_hit(top_hit),
            "raw_excerpt_included": False,
            "private_notes_included": False,
        },
        "review_readiness": {
            "cards_ready": len(review_cards),
            "due_cards_ready": len(due_records),
            "first_due_card_id": str(due_records[0].get("question_id", "")) if due_records else "",
            "full_questions_included": False,
        },
        "readiness": {
            "multi_source_intake_ready": source_count >= 2 and len(source_items) >= 2,
            "recall_grounded_in_store": len(recall_results) > 0,
            "review_queue_ready": len(due_records) > 0,
            "scenario_shareable": True,
        },
        "boundaries": {
            "live_source_fetch": "not_required",
            "cloud_llm": "not_required",
            "private_reading_history": "not_included",
            "credentials": "not_included",
            "personal_annotations": "not_included",
        },
    }


def _build_review_plan(
    *,
    manifest: dict[str, Any],
    source_items: list[dict[str, Any]],
    review_cards: list[dict[str, Any]],
    srs_records: list[dict[str, Any]],
) -> dict[str, Any]:
    date = str(manifest.get("date") or "")
    by_question_id = {str(card.get("question_id", "")): idx for idx, card in enumerate(review_cards)}
    source_by_idx = {
        idx: {
            "title": str(item.get("title", "")),
            "source": str(item.get("source", "")),
            "category": str(item.get("category", "")),
            "content_hash": _content_hash(item),
        }
        for idx, item in enumerate(source_items)
    }
    items: list[dict[str, Any]] = []
    for record in _due_records(srs_records, date):
        question_id = str(record.get("question_id", ""))
        source_meta = source_by_idx.get(by_question_id.get(question_id, -1), {})
        items.append(
            {
                "question_id": question_id,
                "source_title": source_meta.get("title", ""),
                "source": source_meta.get("source", ""),
                "category": source_meta.get("category", ""),
                "content_hash": source_meta.get("content_hash", ""),
                "due_date": str(record.get("due_date", "")),
                "ease_factor": float(record.get("ease_factor", 0.0)),
                "interval_days": int(record.get("interval_days", 0)),
                "full_question_included": False,
                "raw_source_excerpt_included": False,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "synthetic_recall_review_plan",
        "date": date,
        "query": manifest.get("query", ""),
        "data_policy": "synthetic_only",
        "private_data_included": False,
        "external_network": False,
        "llm_provider": "stub_or_disabled",
        "items": items,
    }


def _due_records(records: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    if not day:
        return []
    on = _dt.date.fromisoformat(day)
    due = [
        record
        for record in records
        if _dt.date.fromisoformat(str(record.get("due_date", day))) <= on
    ]
    return sorted(due, key=lambda record: (str(record.get("due_date", "")), str(record.get("question_id", ""))))


def _safe_hit(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "title": str(row.get("title", "")),
        "source": str(row.get("source", "")),
        "category": str(row.get("category", "")),
        "link": str(row.get("link", "")),
        "content_hash": _content_hash(row),
    }


def _summary(scenario: dict[str, Any]) -> str:
    coverage = scenario["coverage"]
    top = scenario["recall"]["top_hit"]
    return (
        "# Knowledge scenario proof\n\n"
        f"- Query: {scenario['query']}\n"
        f"- Sources represented: {coverage['source_count']}\n"
        f"- Items captured: {coverage['captured_entries']}\n"
        f"- Recall hits: {coverage['recall_hits']}\n"
        f"- Top recall hit: {top.get('title', '')}\n"
        f"- Due review cards: {coverage['due_cards']}\n"
        "- Boundary: synthetic fixture metadata only; no live feeds, "
        "private reading history, credentials, account notes, raw source "
        "excerpts, or cloud LLM output.\n"
    )


def _content_hash(item: dict[str, Any]) -> str:
    stable = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _bundle_path(root: Path, rel: str) -> Path:
    candidate = Path(rel)
    if candidate.is_absolute():
        raise RuntimeError("knowledge-scenario artifact paths must be bundle-relative")
    root_resolved = root.resolve()
    path = (root / candidate).resolve()
    try:
        path.relative_to(root_resolved)
    except ValueError as exc:
        raise RuntimeError("knowledge-scenario artifact paths must stay inside the bundle") from exc
    return path


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="write deterministic knowledge intake / recall-SRS scenario artifacts"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        path = write_knowledge_scenario_bundle(source_bundle=args.source, out_root=args.out)
    except (RuntimeError, ValueError) as exc:
        print(f"knowledge-scenario: {exc}", file=sys.stderr)
        return 1
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "write_knowledge_scenario_bundle"]
