"""Deterministic source adapter / collection / review export bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def write_source_export_bundle(
    *,
    source_bundle: str | Path,
    out_root: str | Path,
) -> Path:
    """Write a deterministic export bundle from a safe synthetic demo-loop bundle."""
    source = Path(source_bundle)
    out = Path(out_root)
    source_root, manifest = _load_source_manifest(source)
    _validate_source_manifest(manifest)

    artifacts = manifest.get("artifacts") or {}
    source_items = _load_jsonl_artifact(source_root, artifacts, "source_items")
    recall_results = _load_json_artifact(source_root, artifacts, "recall_results", default=[])
    review_cards = _load_json_artifact(source_root, artifacts, "review_cards", default=[])

    adapter_contract = _adapter_contract()
    collection_export = _collection_export(
        manifest=manifest,
        source_items=source_items,
        recall_results=recall_results,
    )
    review_export = _review_export(
        manifest=manifest,
        source_items=source_items,
        review_cards=review_cards,
    )

    out.mkdir(parents=True, exist_ok=True)
    adapter_path = out / "source-adapter-contract.json"
    collection_path = out / "collection-export.json"
    review_path = out / "review-export.json"
    summary_path = out / "summary.md"
    adapter_path.write_text(_json(adapter_contract), encoding="utf-8")
    collection_path.write_text(_json(collection_export), encoding="utf-8")
    review_path.write_text(_json(review_export), encoding="utf-8")
    summary_path.write_text(
        _summary(collection_export, review_export),
        encoding="utf-8",
    )

    out_manifest = {
        "schema_version": SCHEMA_VERSION,
        "mode": "synthetic_source_export_bundle",
        "source_mode": manifest.get("mode", ""),
        "date": manifest.get("date", ""),
        "query": manifest.get("query", ""),
        "data_policy": "synthetic_only",
        "private_data_included": False,
        "external_network": False,
        "llm_provider": "stub_or_disabled",
        "live_sources_required": False,
        "artifacts": {
            "adapter_contract": _rel(out, adapter_path),
            "collection_export": _rel(out, collection_path),
            "review_export": _rel(out, review_path),
            "summary": _rel(out, summary_path),
        },
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(_json(out_manifest), encoding="utf-8")
    return manifest_path


def _load_source_manifest(source: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = source if source.is_file() else source / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("source-export requires a demo-loop manifest.json")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("source-export manifest must be a JSON object")
    return manifest_path.parent, raw


def _validate_source_manifest(manifest: dict[str, Any]) -> None:
    if (
        manifest.get("mode") != "synthetic_knowledge_intake_loop"
        or manifest.get("data_policy") != "synthetic_only"
        or manifest.get("private_data_included") is not False
        or manifest.get("external_network") is not False
        or manifest.get("llm_provider") != "stub_or_disabled"
    ):
        raise RuntimeError("source-export only accepts safe synthetic demo-loop bundles")


def _load_json_artifact(
    source: Path,
    artifacts: dict[str, Any],
    key: str,
    *,
    default: Any,
) -> Any:
    rel = artifacts.get(key)
    if not isinstance(rel, str):
        return default
    path = _bundle_path(source, rel)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl_artifact(
    source: Path,
    artifacts: dict[str, Any],
    key: str,
) -> list[dict[str, Any]]:
    rel = artifacts.get(key)
    if not isinstance(rel, str):
        return []
    path = _bundle_path(source, rel)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _adapter_contract() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "source_adapter_contract",
        "data_policy": "synthetic_or_public_only",
        "default_live_fetch": "disabled",
        "network_required_for_tests": False,
        "required_fields": [
            "source_id",
            "source_type",
            "fetch_policy",
            "license_note",
            "citation_policy",
            "output_schema",
        ],
        "source_types": [
            "fixture",
            "rss",
            "web_page",
            "newsletter_export",
            "paper_metadata",
        ],
        "output_schema": {
            "title": "string",
            "summary_excerpt": "string",
            "link": "string",
            "source": "string",
            "category": "string",
        },
        "adapter_rules": [
            "tests use fixture/offline data",
            "live fetch is explicit opt-in",
            "outputs include citation metadata",
            "private account material is not committed",
        ],
    }


def _collection_export(
    *,
    manifest: dict[str, Any],
    source_items: list[dict[str, Any]],
    recall_results: list[dict[str, Any]],
) -> dict[str, Any]:
    hit_titles = {
        str(row.get("title", ""))
        for row in recall_results
        if isinstance(row, dict)
    }
    items = []
    for item in source_items:
        title = str(item.get("title", ""))
        summary_excerpt = str(item.get("summary_excerpt", ""))
        items.append(
            {
                "title": title,
                "source": str(item.get("source", "")),
                "category": str(item.get("category", "")),
                "link": str(item.get("link", "")),
                "summary_excerpt": summary_excerpt,
                "content_hash": _content_hash(item),
                "source_policy": "synthetic_fixture",
                "matched_query": title in hit_titles,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "synthetic_collection_export",
        "date": manifest.get("date", ""),
        "query": manifest.get("query", ""),
        "data_policy": "synthetic_only",
        "private_data_included": False,
        "external_network": False,
        "source_count": len({item["source"] for item in items}),
        "item_count": len(items),
        "items": items,
    }


def _review_export(
    *,
    manifest: dict[str, Any],
    source_items: list[dict[str, Any]],
    review_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    titles = [str(item.get("title", "")) for item in source_items]
    cards = []
    for idx, card in enumerate(review_cards):
        if not isinstance(card, dict):
            continue
        cards.append(
            {
                "question_id": str(card.get("question_id", "")),
                "question": str(card.get("question", "")),
                "source_title": titles[idx] if idx < len(titles) else "",
                "review_policy": "synthetic_spaced_review",
            }
        )
    counts = manifest.get("counts") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "synthetic_review_export",
        "date": manifest.get("date", ""),
        "data_policy": "synthetic_only",
        "private_data_included": False,
        "external_network": False,
        "card_count": len(cards),
        "due_count": int(counts.get("due_cards") or 0),
        "cards": cards,
    }


def _summary(collection: dict[str, Any], review: dict[str, Any]) -> str:
    return (
        "# Source export bundle\n\n"
        f"- Collection items: {collection['item_count']}\n"
        f"- Sources represented: {collection['source_count']}\n"
        f"- Review cards: {review['card_count']}\n"
        f"- Due cards: {review['due_count']}\n"
        "- Boundary: synthetic fixture exports only; live fetching and account "
        "material stay outside this bundle.\n"
    )


def _content_hash(item: dict[str, Any]) -> str:
    stable = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _bundle_path(root: Path, rel: str) -> Path:
    candidate = Path(rel)
    if candidate.is_absolute():
        raise RuntimeError("source-export artifact paths must be bundle-relative")
    root_resolved = root.resolve()
    path = (root / candidate).resolve()
    try:
        path.relative_to(root_resolved)
    except ValueError as exc:
        raise RuntimeError("source-export artifact paths must stay inside the bundle") from exc
    return path


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="write deterministic source adapter/export artifacts"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        path = write_source_export_bundle(source_bundle=args.source, out_root=args.out)
    except (RuntimeError, ValueError) as exc:
        print(f"source-export: {exc}", file=sys.stderr)
        return 1
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "write_source_export_bundle"]
