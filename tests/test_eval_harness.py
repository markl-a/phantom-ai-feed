"""Eval-harness tests: assert metrics are COMPUTED and well-formed.

These tests deliberately do NOT assert the generated questions pass any
quality bar — that requires the owner's real ~20-question gold set, which
is supplied later via ``--gold``. They only prove the harness runs
end-to-end on the shipped *synthetic* placeholder gold set and emits
numbers in range with the expected keys.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import eval as ev  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLD_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gold_sample.jsonl"

# A stub batch of generated interview questions (what the generator emits,
# already split into individual question strings).
STUB_GENERATED = [
    "Explain Transformers at a level a senior ML engineer would expect; "
    "include one failure mode you have seen in production.",
    "Walk through how you would build an offline benchmark for RAG; "
    "what metric correlates best with user-perceived quality?",
    "Compare two real implementations of Quantization; where do their "
    "assumptions diverge?",
    "If Agents regressed 15% over a week, what is your debugging tree "
    "(top 3 branches)?",
    "Design a 30-minute on-prem demo of Evaluation for a non-ML "
    "stakeholder; what do you cut, what stays?",
]

STUB_DIGEST_TOPICS = ["Transformers", "RAG", "Quantization", "Agents", "Evaluation"]


def test_gold_fixture_exists_and_parses():
    assert GOLD_FIXTURE.exists(), "synthetic gold fixture must ship"
    gold = ev.load_gold(GOLD_FIXTURE)
    assert len(gold) >= 3
    for row in gold:
        assert set(row.keys()) >= {"question", "category", "topic_tags"}
        assert isinstance(row["question"], str) and row["question"]
        assert isinstance(row["category"], str)
        assert isinstance(row["topic_tags"], list)


def test_token_f1_and_jaccard_in_range():
    assert ev._token_f1("a b c", "a b c") == 1.0
    assert ev._token_f1("a b c", "x y z") == 0.0
    j = ev._jaccard({"a", "b"}, {"b", "c"})
    assert 0.0 <= j <= 1.0


def test_classify_category_returns_known_label():
    label = ev.classify_category("If X regressed 15%, what is your debugging tree?")
    assert label in ev.CATEGORIES


def test_near_duplicate_detection_flags_obvious_dup():
    qs = [
        "Explain how RAG retrieval works in production systems.",
        "Explain how RAG retrieval works in production systems.",
        "Design an on-prem demo of quantization for a stakeholder.",
    ]
    dups = ev.near_duplicates(qs, threshold=0.8)
    assert any(set(p["pair"]) == {0, 1} for p in dups)


def test_evaluate_well_formed_metrics():
    gold = ev.load_gold(GOLD_FIXTURE)
    report = ev.evaluate(
        STUB_GENERATED, gold, digest_topics=STUB_DIGEST_TOPICS
    )
    # top-level keys present
    for key in ("coverage", "category_mix", "near_duplicates", "n_generated"):
        assert key in report, f"missing metric block: {key}"

    cov = report["coverage"]
    for key in ("digest_topic_coverage", "gold_topic_coverage", "mean_max_f1_vs_gold"):
        assert key in cov
        assert 0.0 <= cov[key] <= 1.0, f"{key} out of [0,1]: {cov[key]}"

    mix = report["category_mix"]
    assert "generated_distribution" in mix
    assert "gold_distribution" in mix
    assert "l1_distance" in mix
    # distributions sum to ~1 (or 0 if empty) and cover the known categories
    gen_dist = mix["generated_distribution"]
    assert set(gen_dist.keys()) == set(ev.CATEGORIES)
    assert abs(sum(gen_dist.values()) - 1.0) < 1e-6
    assert 0.0 <= mix["l1_distance"] <= 2.0

    assert isinstance(report["near_duplicates"], list)
    assert report["n_generated"] == len(STUB_GENERATED)


def test_evaluate_handles_empty_generated():
    gold = ev.load_gold(GOLD_FIXTURE)
    report = ev.evaluate([], gold, digest_topics=[])
    assert report["n_generated"] == 0
    # must not crash; metrics still present and in-range
    assert 0.0 <= report["coverage"]["mean_max_f1_vs_gold"] <= 1.0


def test_cli_runs_on_default_synthetic_gold(tmp_path):
    """End-to-end CLI: defaults to the shipped synthetic gold, emits JSON."""
    gen_file = tmp_path / "weekly-questions-2026-06-13.md"
    gen_file.write_text(
        "# weekly interview questions\n\n"
        + "\n".join(f"{i}. {q}" for i, q in enumerate(STUB_GENERATED, 1))
        + "\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "phantom_ai_feed.eval",
            "--generated",
            str(gen_file),
            "--json",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["gold_source"].endswith("gold_sample.jsonl")
    assert payload["gold_is_synthetic"] is True
    assert "coverage" in payload and "category_mix" in payload


def test_cli_accepts_custom_gold(tmp_path):
    """Owner drops in a real gold file via --gold with ZERO code change."""
    custom = tmp_path / "real_gold.jsonl"
    custom.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {
                    "question": "Derive the attention softmax gradient.",
                    "category": "conceptual",
                    "topic_tags": ["transformers", "attention"],
                },
                {
                    "question": "Design a sharded vector store for 1B vectors.",
                    "category": "system-design",
                    "topic_tags": ["rag", "vector-db"],
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gen_file = tmp_path / "gen.md"
    gen_file.write_text("1. Explain attention in transformers.\n", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "phantom_ai_feed.eval",
            "--generated",
            str(gen_file),
            "--gold",
            str(custom),
            "--json",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["gold_source"].endswith("real_gold.jsonl")
    assert payload["gold_is_synthetic"] is False
