"""P3.1 — eval gold-set calibration + question-generation quality grading.

Two things this proves that the original ``test_eval_harness`` did not:

  1. A REAL ~20-question gold set ships (``tests/fixtures/gold_real.jsonl``),
     NOT the synthetic placeholder. It is well-formed, balanced across the
     three categories, and carries no "SYNTHETIC PLACEHOLDER" marker.

  2. A GRADING loop with actual quality BARS: when the interview-question
     generator runs over a realistic week of digests, the eval harness scores
     it and the batch must clear minimum coverage / category-balance /
     non-duplication thresholds calibrated against the real gold. This turns
     the harness from "computes numbers" into "passes/fails a quality bar".

All hermetic — the generator runs in stub mode (no LLM), pure stdlib eval.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import eval as ev  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_GOLD = REPO_ROOT / "tests" / "fixtures" / "gold_real.jsonl"


# --------------------------------------------------------------------------- #
# 1. the real gold set                                                        #
# --------------------------------------------------------------------------- #
def test_real_gold_exists_and_is_substantial():
    assert REAL_GOLD.exists(), "real (non-synthetic) gold set must ship"
    gold = ev.load_gold(REAL_GOLD)
    assert len(gold) >= 18, f"expected ~20 questions, got {len(gold)}"


def test_real_gold_not_synthetic_placeholder():
    text = REAL_GOLD.read_text(encoding="utf-8")
    assert "SYNTHETIC PLACEHOLDER" not in text
    assert "not a real interview standard" not in text


def test_real_gold_well_formed_rows():
    gold = ev.load_gold(REAL_GOLD)
    for row in gold:
        assert isinstance(row["question"], str) and len(row["question"]) > 20
        assert ev._normalise_category(row["category"]) in ev.CATEGORIES
        assert isinstance(row["topic_tags"], list) and row["topic_tags"]
        assert all(isinstance(t, str) and t for t in row["topic_tags"])


def test_real_gold_balanced_across_categories():
    gold = ev.load_gold(REAL_GOLD)
    labels = [ev._normalise_category(r["category"]) for r in gold]
    counts = {c: labels.count(c) for c in ("conceptual", "system-design",
                                           "debugging")}
    # every core category is represented and none dominates (>70%).
    assert all(n >= 3 for n in counts.values()), counts
    assert max(counts.values()) / len(gold) <= 0.7, counts


def test_real_gold_has_no_internal_near_duplicates():
    gold = ev.load_gold(REAL_GOLD)
    questions = [r["question"] for r in gold]
    dups = ev.near_duplicates(questions, threshold=0.8)
    assert not dups, f"gold set has near-duplicate questions: {dups}"


# --------------------------------------------------------------------------- #
# 2. grading loop with quality bars                                           #
# --------------------------------------------------------------------------- #
def _generate_week_questions():
    """Run the real interview-question generator (stub mode) over a realistic
    week of digests and return the parsed question strings."""
    import datetime as _dt
    import tempfile
    from phantom_ai_feed import interview_questions as iq

    topics = ["Transformers", "RAG", "Quantization", "Agents",
              "Evaluation", "Inference-Serving"]
    with tempfile.TemporaryDirectory() as d:
        log_dir = Path(d)
        end = _dt.date(2026, 6, 13)
        # six daily digests, each surfacing two topic sections
        for i in range(6):
            day = end - _dt.timedelta(days=i)
            t1, t2 = topics[i % len(topics)], topics[(i + 1) % len(topics)]
            (log_dir / f"{day.isoformat()}.md").write_text(
                f"# digest {day}\n\n## {t1}\nbody\n\n## {t2}\nbody\n",
                encoding="utf-8",
            )
        out = iq.run(log_dir=log_dir, end=end, use_stub=True)
        return ev.parse_generated_questions(out.read_text(encoding="utf-8"))


def test_generator_output_grades_against_real_gold():
    gold = ev.load_gold(REAL_GOLD)
    generated = _generate_week_questions()
    assert generated, "generator produced no questions"

    report = ev.evaluate(generated, gold, digest_topics=[
        "Transformers", "RAG", "Quantization", "Agents", "Evaluation",
        "Inference-Serving",
    ])

    # QUALITY BAR 1 — coverage: the batch must talk about the week's topics.
    assert report["coverage"]["digest_topic_coverage"] >= 0.5, report["coverage"]

    # QUALITY BAR 2 — category balance: the generated batch must span at least
    # two of the three core categories (not all one-note).
    gen_dist = report["category_mix"]["generated_distribution"]
    nonzero_core = sum(
        1 for c in ("conceptual", "system-design", "debugging")
        if gen_dist.get(c, 0) > 0
    )
    assert nonzero_core >= 2, gen_dist

    # QUALITY BAR 3 — non-duplication: no two generated questions are near-dups.
    assert not report["near_duplicates"], report["near_duplicates"]


def test_grade_helper_returns_pass_fail_verdict():
    """A new ``grade`` helper applies the calibrated bars and yields a verdict
    dict (passed: bool + per-bar booleans) so the owner can gate on it."""
    gold = ev.load_gold(REAL_GOLD)
    generated = _generate_week_questions()
    verdict = ev.grade(generated, gold, digest_topics=[
        "Transformers", "RAG", "Quantization", "Agents", "Evaluation",
        "Inference-Serving",
    ])
    assert set(verdict) >= {"passed", "bars", "report"}
    assert isinstance(verdict["passed"], bool)
    assert verdict["passed"] is True
    assert all(isinstance(v, bool) for v in verdict["bars"].values())


def test_grade_fails_on_empty_batch():
    gold = ev.load_gold(REAL_GOLD)
    verdict = ev.grade([], gold, digest_topics=["Transformers"])
    assert verdict["passed"] is False


def test_cli_grade_against_real_gold_passes(tmp_path):
    """End-to-end CLI: --real-gold --grade on a good batch exits 0 PASS."""
    import json
    import subprocess

    generated = _generate_week_questions()
    gen_file = tmp_path / "weekly-questions-2026-06-13.md"
    gen_file.write_text(
        "# weekly interview questions\n\n"
        + "\n".join(f"{i}. {q}" for i, q in enumerate(generated, 1))
        + "\n",
        encoding="utf-8",
    )
    digest_file = tmp_path / "digest.md"
    digest_file.write_text(
        "# digest\n\n## Transformers\nx\n\n## RAG\ny\n\n## Quantization\nz\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "phantom_ai_feed.eval",
         "--generated", str(gen_file), "--digest", str(digest_file),
         "--real-gold", "--grade", "--json"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["gold_source"].endswith("gold_real.jsonl")
    assert payload["gold_is_synthetic"] is False
    assert payload["grade"]["passed"] is True


def test_cli_grade_fails_exit_nonzero_on_empty(tmp_path):
    """--grade with no --generated (empty batch) exits non-zero (FAIL)."""
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "phantom_ai_feed.eval",
         "--real-gold", "--grade", "--json"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 1, proc.stdout
