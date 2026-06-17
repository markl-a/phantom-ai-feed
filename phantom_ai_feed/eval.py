"""Dependency-free eval harness for generated interview questions.

Scores a batch of *generated* interview questions (from
``phantom_ai_feed.interview_questions``) against a GOLD set on three axes:

1. **coverage** — token overlap (Jaccard / token-F1) between the generated
   questions and (a) the week's digest topics and (b) the gold set's topics.
   "Does the batch actually talk about what it should?"
2. **category mix** — the distribution of generated questions across
   ``conceptual`` / ``system-design`` / ``debugging`` vs. the gold's, with an
   L1 distance. "Is the batch lopsided?"
3. **near-duplicate detection** — pairwise token-Jaccard among the generated
   questions to flag redundancy. "Did it ask the same thing twice?"

This is a *lightweight, honest proxy*, NOT a public benchmark and NOT a model
eval — pure Python stdlib, no GPU, no model download, no external deps. The
harness only *computes and reports* numbers; whether a batch passes a quality
bar is a judgement that requires the owner's real gold set (supplied later via
``--gold``). The numbers are real and computed from the data.

GOLD-SET FILE FORMAT (JSONL — one object per line)::

    {"question": str, "category": str, "topic_tags": [str]}

A small *synthetic placeholder* gold set ships at
``tests/fixtures/gold_sample.jsonl`` so the harness runs end-to-end in CI.
Drop the real ~20-question gold set in via ``--gold <path>`` with zero code
change.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_WORD = re.compile(r"\w+")

# Canonical category labels. The gold set's `category` values are normalised
# (lower-cased, spaces/underscores → hyphen) into one of these; unknown values
# fall through to "other".
CATEGORIES: tuple[str, ...] = ("conceptual", "system-design", "debugging", "other")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLD = REPO_ROOT / "tests" / "fixtures" / "gold_sample.jsonl"

# A leading "1." / "2)" / "- " markdown list marker on a generated question.
_LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+")
# Italic stub/meta annotation lines we should not treat as questions.
_META_LINE = re.compile(r"^\s*_.*_\s*$")


# --------------------------------------------------------------------------- #
# stdlib token primitives (same dependency-free pattern as phantom_training)
# --------------------------------------------------------------------------- #
def _tokens(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _token_f1(pred: str, gold: str) -> float:
    pt, gt = _tokens(pred), _tokens(gold)
    if not pt and not gt:
        return 1.0
    if not pt or not gt:
        return 0.0
    gt_counts: dict[str, int] = {}
    for t in gt:
        gt_counts[t] = gt_counts.get(t, 0) + 1
    overlap = 0
    seen: dict[str, int] = {}
    for t in pt:
        seen[t] = seen.get(t, 0) + 1
        if seen[t] <= gt_counts.get(t, 0):
            overlap += 1
    if overlap == 0:
        return 0.0
    precision = overlap / len(pt)
    recall = overlap / len(gt)
    return 2 * precision * recall / (precision + recall)


# --------------------------------------------------------------------------- #
# loading / parsing
# --------------------------------------------------------------------------- #
def load_gold(path: Path | str) -> list[dict[str, Any]]:
    """Load the JSONL gold set. Each row: {question, category, topic_tags}."""
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows.append(
                {
                    "question": str(obj.get("question", "")),
                    "category": str(obj.get("category", "")),
                    "topic_tags": list(obj.get("topic_tags", []) or []),
                }
            )
    return rows


def parse_generated_questions(md_text: str) -> list[str]:
    """Extract individual question strings from a weekly-questions .md body.

    Pulls numbered / bulleted list items; skips headers (``#``) and italic
    meta lines (``_..._``). Lines without a marker but with content are kept
    too, so a plain list still parses.
    """
    out: list[str] = []
    for raw in (md_text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or _META_LINE.match(line):
            continue
        stripped = _LIST_MARKER.sub("", line)
        if stripped:
            out.append(stripped.strip())
    return out


# digest "topics" are the `## <name>` section headers (matching the same
# regex interview_questions.py uses to mine topics from the week's digests).
_TOPIC_RE = re.compile(r"##\s+(\S[^_\n]+)")


def extract_digest_topics(md_text: str) -> list[str]:
    return [m.strip() for m in _TOPIC_RE.findall(md_text or "")]


# --------------------------------------------------------------------------- #
# category classification
# --------------------------------------------------------------------------- #
def _normalise_category(label: str) -> str:
    norm = re.sub(r"[\s_]+", "-", (label or "").strip().lower())
    return norm if norm in CATEGORIES else "other"


# Heuristic keyword cues for classifying a *generated* question whose category
# is not labelled. Deliberately simple and transparent — order matters
# (debugging cues checked before design/conceptual).
_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("debugging", ("debug", "regress", "dropped", "isolate the cause",
                   "root cause", "lost", "failure mode", "why is", "troubleshoot")),
    ("system-design", ("design", "architect", "build an", "build a", "scale",
                       "throughput", "cluster", "serving", "pipeline", "demo of")),
    ("conceptual", ("explain", "compare", "derive", "what is", "describe",
                    "difference between", "walk through how")),
)


def classify_category(question: str) -> str:
    """Heuristically bucket a generated question into a CATEGORIES label."""
    q = (question or "").lower()
    for label, cues in _CUES:
        if any(cue in q for cue in cues):
            return label
    return "other"


def _distribution(labels: list[str]) -> dict[str, float]:
    counts = Counter(labels)
    total = sum(counts.values())
    if not total:
        return {c: 0.0 for c in CATEGORIES}
    return {c: round(counts.get(c, 0) / total, 4) for c in CATEGORIES}


def _l1(a: dict[str, float], b: dict[str, float]) -> float:
    return round(sum(abs(a.get(c, 0.0) - b.get(c, 0.0)) for c in CATEGORIES), 4)


# --------------------------------------------------------------------------- #
# metric blocks
# --------------------------------------------------------------------------- #
def coverage(
    generated: list[str],
    gold: list[dict[str, Any]],
    digest_topics: list[str],
) -> dict[str, Any]:
    """Topic-overlap coverage of the generated batch.

    - ``digest_topic_coverage``: fraction of digest topics whose token set has
      non-zero Jaccard overlap with at least one generated question.
    - ``gold_topic_coverage``: same, against the union of gold topic_tags.
    - ``mean_max_f1_vs_gold``: mean over generated questions of the best
      token-F1 against any gold question (semantic-ish proximity proxy).
    """
    gen_token_sets = [set(_tokens(q)) for q in generated]

    def _topic_hit(topic: str) -> bool:
        tset = set(_tokens(topic))
        if not tset:
            return False
        return any(_jaccard(tset, g) > 0.0 for g in gen_token_sets)

    dt = [t for t in digest_topics if t.strip()]
    digest_cov = (
        round(sum(_topic_hit(t) for t in dt) / len(dt), 4) if dt else 0.0
    )

    gold_tags = sorted({tag for row in gold for tag in row["topic_tags"] if tag})
    gold_cov = (
        round(sum(_topic_hit(t) for t in gold_tags) / len(gold_tags), 4)
        if gold_tags
        else 0.0
    )

    gold_questions = [row["question"] for row in gold]
    if generated and gold_questions:
        per = [max(_token_f1(q, gq) for gq in gold_questions) for q in generated]
        mean_max_f1 = round(sum(per) / len(per), 4)
    else:
        mean_max_f1 = 0.0

    return {
        "digest_topic_coverage": digest_cov,
        "gold_topic_coverage": gold_cov,
        "mean_max_f1_vs_gold": mean_max_f1,
        "n_digest_topics": len(dt),
        "n_gold_tags": len(gold_tags),
    }


def category_mix(
    generated: list[str], gold: list[dict[str, Any]]
) -> dict[str, Any]:
    gen_labels = [classify_category(q) for q in generated]
    gold_labels = [_normalise_category(r["category"]) for r in gold]
    gen_dist = _distribution(gen_labels)
    gold_dist = _distribution(gold_labels)
    return {
        "generated_distribution": gen_dist,
        "gold_distribution": gold_dist,
        "l1_distance": _l1(gen_dist, gold_dist),
        "generated_labels": gen_labels,
    }


def near_duplicates(
    generated: list[str], *, threshold: float = 0.8
) -> list[dict[str, Any]]:
    """Flag pairs of generated questions with token-Jaccard >= threshold."""
    sets = [set(_tokens(q)) for q in generated]
    dups: list[dict[str, Any]] = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            sim = _jaccard(sets[i], sets[j])
            if sim >= threshold:
                dups.append({"pair": [i, j], "jaccard": round(sim, 4)})
    return dups


def evaluate(
    generated: list[str],
    gold: list[dict[str, Any]],
    *,
    digest_topics: list[str] | None = None,
    dup_threshold: float = 0.8,
) -> dict[str, Any]:
    """Run all three metric blocks. Pure computation — no pass/fail verdict."""
    digest_topics = digest_topics or []
    return {
        "n_generated": len(generated),
        "n_gold": len(gold),
        "coverage": coverage(generated, gold, digest_topics),
        "category_mix": category_mix(generated, gold),
        "near_duplicates": near_duplicates(generated, threshold=dup_threshold),
        "dup_threshold": dup_threshold,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _render_text(report: dict[str, Any]) -> str:
    cov = report["coverage"]
    mix = report["category_mix"]
    lines = [
        "phantom-ai-feed interview-question eval (synthetic-fixture proxy; "
        "not a real interview standard)",
        f"  gold source        : {report['gold_source']}"
        + ("  [SYNTHETIC PLACEHOLDER]" if report["gold_is_synthetic"] else "  [owner-supplied]"),
        f"  generated questions: {report['n_generated']}",
        f"  gold questions     : {report['n_gold']}",
        "  coverage:",
        f"    digest_topic_coverage : {cov['digest_topic_coverage']}"
        f"  ({cov['n_digest_topics']} topics)",
        f"    gold_topic_coverage   : {cov['gold_topic_coverage']}"
        f"  ({cov['n_gold_tags']} tags)",
        f"    mean_max_f1_vs_gold   : {cov['mean_max_f1_vs_gold']}",
        "  category_mix:",
        f"    generated : {mix['generated_distribution']}",
        f"    gold      : {mix['gold_distribution']}",
        f"    l1_distance: {mix['l1_distance']}",
        f"  near_duplicates (>= {report['dup_threshold']}): "
        f"{len(report['near_duplicates'])} pair(s) {report['near_duplicates']}",
    ]
    return "\n".join(lines)


def run_cli(
    generated_path: Path | None,
    gold_path: Path,
    digest_path: Path | None,
    *,
    dup_threshold: float = 0.8,
) -> dict[str, Any]:
    gold = load_gold(gold_path)
    if generated_path is not None:
        generated = parse_generated_questions(
            Path(generated_path).read_text(encoding="utf-8")
        )
    else:
        generated = []
    digest_topics: list[str] = []
    if digest_path is not None:
        digest_topics = extract_digest_topics(
            Path(digest_path).read_text(encoding="utf-8")
        )
    report = evaluate(
        generated, gold, digest_topics=digest_topics, dup_threshold=dup_threshold
    )
    report["gold_source"] = str(gold_path)
    report["gold_is_synthetic"] = Path(gold_path).resolve() == DEFAULT_GOLD.resolve()
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Eval harness for generated interview questions. Computes coverage / "
            "category-mix / near-duplicate metrics against a JSONL gold set. "
            "Defaults to a SYNTHETIC placeholder gold set; supply the real one "
            "with --gold (zero code change)."
        )
    )
    ap.add_argument(
        "--gold",
        type=Path,
        default=DEFAULT_GOLD,
        help="JSONL gold set {question, category, topic_tags}. "
        "Default: synthetic placeholder shipped in tests/fixtures/.",
    )
    ap.add_argument(
        "--generated",
        type=Path,
        default=None,
        help="weekly-questions-*.md produced by interview_questions. "
        "If omitted, an empty batch is scored.",
    )
    ap.add_argument(
        "--digest",
        type=Path,
        default=None,
        help="optional daily/weekly digest .md to mine topic coverage against.",
    )
    ap.add_argument("--dup-threshold", type=float, default=0.8)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args(argv)

    report = run_cli(
        args.generated, args.gold, args.digest, dup_threshold=args.dup_threshold
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
