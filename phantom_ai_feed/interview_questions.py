"""Weekly interview-question generator.

Reads the last 6 daily digest .md files (Mon-Sat) from
~/.phantom-mesh/logs/phantom-ai-feed/, asks Gemini to produce 5 ML/AI
engineering interview questions grounded in the week's stories, and
writes them to `weekly-questions-<sat-date>.md` in the same dir.

Stub mode (--use-stub or no API key): emits a templated question bank
derived from the most-mentioned source names — enough for end-to-end
smoke tests without burning credits.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import sys
from collections import Counter
from pathlib import Path

from . import summarize as _sum

DEFAULT_LOG_DIR = Path.home() / ".phantom-mesh" / "logs" / "phantom-ai-feed"
_TOPIC_RE = re.compile(r"##\s+(\S[^_\n]+)")


def _collect_week(log_dir: Path, end: _dt.date, days: int = 6) -> list[tuple[_dt.date, str]]:
    out: list[tuple[_dt.date, str]] = []
    for i in range(days):
        d = end - _dt.timedelta(days=i)
        p = log_dir / f"{d.isoformat()}.md"
        if p.exists():
            out.append((d, p.read_text("utf-8")))
    return list(reversed(out))


def _stub_questions(week: list[tuple[_dt.date, str]]) -> str:
    topics: Counter[str] = Counter()
    for _, text in week:
        for m in _TOPIC_RE.findall(text):
            topics[m.strip()] += 1
    top = [t for t, _ in topics.most_common(5)] or [
        "Transformers", "RAG", "Quantization", "Agents", "Evaluation",
    ]
    bank = [
        "Explain {} at a level a senior ML engineer would expect; "
        "include one failure mode you have seen in production.",
        "Walk through how you would build an offline benchmark for {}; "
        "what metric correlates best with user-perceived quality?",
        "Compare two real implementations of {}; where do their assumptions diverge?",
        "If {} regressed 15% over a week, what is your debugging tree (top 3 branches)?",
        "Design a 30-minute on-prem demo of {} for a non-ML stakeholder; "
        "what do you cut, what stays?",
    ]
    lines = ["_Stub generator: questions templated from this week's top sources._", ""]
    for i, (q, t) in enumerate(zip(bank, top), 1):
        lines.append(f"{i}. {q.format(t)}")
    return "\n".join(lines)


def _llm_prompt(week: list[tuple[_dt.date, str]]) -> str:
    blob = "\n\n---\n\n".join(f"# {d.isoformat()}\n{txt}" for d, txt in week)
    return (
        "You are an ML hiring manager. Based on the AI-frontier digest "
        "below (one week), write 5 interview questions for a senior "
        "Chinese-speaking ML/AI engineer. Mix conceptual + system-design + "
        "debugging. Use 繁體中文 question stem with English technical terms. "
        "Number them 1-5. Output questions only.\n\n=== WEEK DIGEST ===\n"
        + blob[:18000]
    )


def run(
    log_dir: Path = DEFAULT_LOG_DIR,
    end: _dt.date | None = None,
    *,
    use_stub: bool = False,
) -> Path:
    end = end or _dt.date.today()
    week = _collect_week(log_dir, end)
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / f"weekly-questions-{end.isoformat()}.md"
    if not week:
        body = "_(no digest files found for the past 6 days)_"
    elif use_stub or not os.environ.get("GEMINI_API_KEY"):
        body = _stub_questions(week)
    else:
        body = _sum.summarize(_llm_prompt(week), max_words=600)
    header = f"# phantom-ai-feed weekly interview questions — week ending {end.isoformat()}\n\n"
    out_path.write_text(header + body + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="weekly interview-question generator")
    ap.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    ap.add_argument("--end", type=str, default=None,
                    help="YYYY-MM-DD; defaults to today")
    ap.add_argument("--use-stub", action="store_true")
    args = ap.parse_args(argv)
    end = _dt.date.fromisoformat(args.end) if args.end else None
    run(log_dir=args.log_dir, end=end, use_stub=args.use_stub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
