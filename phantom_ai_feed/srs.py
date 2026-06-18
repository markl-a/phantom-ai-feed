"""Spaced-repetition review log for phantom-ai-feed."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

DEFAULT_STORE = (
    Path.home() / ".phantom-mesh" / "logs" / "phantom-ai-feed" / "srs.jsonl"
)


def _load_latest(store: Path) -> dict[str, dict]:
    if not store.exists():
        return {}

    latest: dict[str, dict] = {}
    with store.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            latest[record["question_id"]] = record
    return latest


def sm2(
    grade: int,
    *,
    ease_factor: float = 2.5,
    interval_days: int = 0,
    repetitions: int = 0,
) -> tuple[float, int, int]:
    if not 0 <= grade <= 5:
        raise ValueError("grade must be between 0 and 5")

    q = grade
    if q < 3:
        reps = 0
        interval = 1
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval_days * ease_factor)
        reps = repetitions + 1
    ef = ease_factor + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    if ef < 1.3:
        ef = 1.3
    return (ef, interval, reps)


def answer(
    store: Path,
    question_id: str,
    grade: int,
    *,
    on: _dt.date | None = None,
    question: str | None = None,
) -> dict:
    on = on or _dt.date.today()
    latest = _load_latest(store)
    previous = latest.get(question_id, {})
    ef, interval, reps = sm2(
        grade,
        ease_factor=previous.get("ease_factor", 2.5),
        interval_days=previous.get("interval_days", 0),
        repetitions=previous.get("repetitions", 0),
    )
    due = on + _dt.timedelta(days=interval)
    record = {
        "question_id": question_id,
        "question": question if question is not None else previous.get("question"),
        "answered_at": on.isoformat(),
        "grade": grade,
        "ease_factor": round(ef, 4),
        "interval_days": interval,
        "repetitions": reps,
        "due_date": due.isoformat(),
    }
    store.parent.mkdir(parents=True, exist_ok=True)
    with store.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def due_cards(store: Path, on: _dt.date) -> list[dict]:
    latest = _load_latest(store)
    due = [
        record
        for record in latest.values()
        if _dt.date.fromisoformat(record["due_date"]) <= on
    ]
    return sorted(due, key=lambda record: (record["due_date"], record["question_id"]))


def register_questions(
    store: Path,
    questions: list[tuple[str, str]],
    *,
    on: _dt.date | None = None,
) -> list[dict]:
    on = on or _dt.date.today()
    latest = _load_latest(store)
    records: list[dict] = []
    for question_id, text in questions:
        if question_id in latest:
            continue
        record = {
            "question_id": question_id,
            "question": text,
            "answered_at": on.isoformat(),
            "grade": 0,
            "ease_factor": 2.5,
            "interval_days": 0,
            "repetitions": 0,
            "due_date": on.isoformat(),
        }
        records.append(record)

    if records:
        store.parent.mkdir(parents=True, exist_ok=True)
        with store.open("a", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record) + "\n")
    return records


def _write_review(out: Path, on: _dt.date, cards: list[dict]) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        fh.write(
            f"# phantom-ai-feed SRS review — due on {on} "
            f"({len(cards)} cards)\n\n"
        )
        for card in cards:
            fh.write(
                f"- {card['question_id']} (due {card['due_date']}, "
                f"ease {card['ease_factor']:.2f}, "
                f"interval {card['interval_days']}d)\n"
            )
            if card.get("question"):
                fh.write(f"  {card['question']}\n")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="phantom-ai-feed SRS")
    sub = ap.add_subparsers(dest="cmd", required=True)

    answer_ap = sub.add_parser("answer")
    answer_ap.add_argument("question_id")
    answer_ap.add_argument("--grade", type=int, required=True, choices=range(0, 6))
    answer_ap.add_argument("--on", default=None)
    answer_ap.add_argument("--store", type=Path, default=DEFAULT_STORE)
    answer_ap.add_argument("--question", default=None)

    due_ap = sub.add_parser("due")
    due_ap.add_argument("--on", default=None)
    due_ap.add_argument("--store", type=Path, default=DEFAULT_STORE)
    due_ap.add_argument("--out", type=Path, default=None)

    args = ap.parse_args(argv)
    on = _dt.date.fromisoformat(args.on) if args.on else None
    on = on or _dt.date.today()

    if args.cmd == "answer":
        record = answer(
            args.store,
            args.question_id,
            args.grade,
            on=on,
            question=args.question,
        )
        print(
            f"recorded {record['question_id']} grade={record['grade']} "
            f"ease={record['ease_factor']:.2f} "
            f"interval={record['interval_days']}d due={record['due_date']}"
        )
        return 0

    if args.out is None:
        args.out = args.store.parent / f"srs-due-{on.isoformat()}.md"
    cards = due_cards(args.store, on)
    _write_review(args.out, on, cards)
    print(f"# phantom-ai-feed SRS review - due on {on} ({len(cards)} cards)")
    for card in cards:
        print(
            f"- {card['question_id']} (due {card['due_date']}, "
            f"ease {card['ease_factor']:.2f}, interval {card['interval_days']}d)"
        )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
