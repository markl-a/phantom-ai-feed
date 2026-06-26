"""Deterministic synthetic ingest -> digest -> recall -> review demo loop."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

from . import srs, store, summarize

SCHEMA_VERSION = 1


def write_synthetic_demo_loop(
    *,
    out_root: str | Path,
    date: str = "2026-06-26",
    query: str = "RAG",
) -> Path:
    """Write a local-only public artifact bundle for the core AI-feed loop."""
    day = _dt.date.fromisoformat(date)
    out = Path(out_root)
    artifacts = out / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    paths = _artifact_paths(artifacts, day)
    _reset(paths)
    items = _synthetic_items()
    _write_jsonl(paths["source_items"], items)

    captured = 0
    for item in items:
        if store.capture(item, db_path=paths["fts_db"], on=day):
            captured += 1

    digest = _render_digest(day, items)
    paths["digest"].write_text(digest, encoding="utf-8")

    raw_recall = store.recall(query, db_path=paths["fts_db"], limit=10)
    recall_rows = _stable_recall(raw_recall, items)
    paths["recall_results"].write_text(
        json.dumps(recall_rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    questions = _review_questions(items, day)
    paths["review_cards"].write_text(
        json.dumps(
            [
                {"question_id": question_id, "question": question}
                for question_id, question in questions
            ],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    registered = srs.register_questions(paths["srs_store"], questions, on=day)
    due = srs.due_cards(paths["srs_store"], day)
    srs._write_review(paths["srs_due"], day, due)

    paths["summary"].write_text(
        _render_summary(day, query, len(items), captured, len(recall_rows), len(due)),
        encoding="utf-8",
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "mode": "synthetic_knowledge_intake_loop",
        "date": day.isoformat(),
        "query": query,
        "data_policy": "synthetic_only",
        "private_data_included": False,
        "external_network": False,
        "llm_provider": "stub_or_disabled",
        "counts": {
            "source_items": len(items),
            "captured_entries": captured,
            "recall_hits": len(recall_rows),
            "review_cards": len(registered),
            "due_cards": len(due),
        },
        "artifacts": {
            "source_items": _rel(out, paths["source_items"]),
            "digest": _rel(out, paths["digest"]),
            "fts_db": _rel(out, paths["fts_db"]),
            "recall_results": _rel(out, paths["recall_results"]),
            "review_cards": _rel(out, paths["review_cards"]),
            "srs_store": _rel(out, paths["srs_store"]),
            "srs_due": _rel(out, paths["srs_due"]),
            "summary": _rel(out, paths["summary"]),
        },
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _artifact_paths(artifacts: Path, day: _dt.date) -> dict[str, Path]:
    return {
        "source_items": artifacts / "source-items.jsonl",
        "digest": artifacts / "digest.md",
        "fts_db": artifacts / "aifeed.db",
        "recall_results": artifacts / "recall-results.json",
        "review_cards": artifacts / "review-cards.json",
        "srs_store": artifacts / "srs.jsonl",
        "srs_due": artifacts / f"srs-due-{day.isoformat()}.md",
        "summary": artifacts / "summary.md",
    }


def _reset(paths: dict[str, Path]) -> None:
    for path in paths.values():
        if path.exists():
            path.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(paths["fts_db"]) + suffix)
        if sidecar.exists():
            sidecar.unlink()


def _synthetic_items() -> list[dict]:
    return [
        {
            "title": "Synthetic RAG evaluation harness",
            "summary_excerpt": (
                "A local evaluation harness compares retrieved context precision "
                "with answer faithfulness for RAG systems."
            ),
            "link": "https://example.invalid/synthetic/rag-eval",
            "source": "synthetic-research",
            "category": "research",
        },
        {
            "title": "Synthetic retrieval grounding checklist",
            "summary_excerpt": (
                "A checklist for debugging stale embeddings, chunk drift, and "
                "generation hallucination in RAG deployments."
            ),
            "link": "https://example.invalid/synthetic/grounding",
            "source": "synthetic-ops",
            "category": "operations",
        },
        {
            "title": "Synthetic inference latency notes",
            "summary_excerpt": (
                "Notes on KV-cache pressure, batching, and tail latency for local "
                "model serving experiments."
            ),
            "link": "https://example.invalid/synthetic/inference",
            "source": "synthetic-serving",
            "category": "serving",
        },
        {
            "title": "Synthetic agent guardrail pattern",
            "summary_excerpt": (
                "A local agent loop uses explicit tool schemas, retry caps, and "
                "human approval before irreversible actions."
            ),
            "link": "https://example.invalid/synthetic/agents",
            "source": "synthetic-agents",
            "category": "agents",
        },
    ]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _render_digest(day: _dt.date, items: list[dict]) -> str:
    lines = [
        f"# Synthetic AI feed digest - {day.isoformat()}",
        "",
        "_Generated from local synthetic fixtures; no network or LLM calls._",
        "",
    ]
    for item in items:
        summary = summarize.summarize_stub(item["summary_excerpt"], max_words=40)
        lines.append(f"## {item['title']}")
        lines.append(f"- Source: {item['source']} ({item['category']})")
        lines.append(f"- Link: {item['link']}")
        lines.append(f"- Summary: {summary}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _stable_recall(rows: list[dict], items: list[dict]) -> list[dict]:
    order = {item["title"]: idx for idx, item in enumerate(items)}
    return sorted(rows, key=lambda row: order.get(row["title"], len(order)))


def _review_questions(items: list[dict], day: _dt.date) -> list[tuple[str, str]]:
    questions = []
    for idx, item in enumerate(items, 1):
        topic = item["title"].removeprefix("Synthetic ").lower()
        questions.append(
            (
                f"{day.isoformat()}-q{idx}",
                f"Synthetic review: explain the key engineering risk in {topic}.",
            )
        )
    return questions


def _render_summary(
    day: _dt.date,
    query: str,
    source_items: int,
    captured: int,
    recall_hits: int,
    due_cards: int,
) -> str:
    return (
        "# Synthetic knowledge intake loop\n\n"
        f"- Date: {day.isoformat()}\n"
        f"- Source items: {source_items}\n"
        f"- Captured into local FTS5: {captured}\n"
        f"- Recall query: {query}\n"
        f"- Recall hits: {recall_hits}\n"
        f"- Due review cards: {due_cards}\n"
        "- Boundary: synthetic local fixtures only; no live source fetch, no "
        "private reading history, no credentials, and no cloud LLM.\n"
    )


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="write a deterministic synthetic AI-feed artifact bundle"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-26")
    parser.add_argument("--query", default="RAG")
    args = parser.parse_args(argv)

    path = write_synthetic_demo_loop(out_root=args.out, date=args.date, query=args.query)
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
