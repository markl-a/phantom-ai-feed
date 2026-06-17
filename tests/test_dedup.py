"""P2.2 — cross-source dedup / topic clustering (unit + integration).

A single story often appears across arXiv, Reddit, and Hacker News. Before
the weekly ranking pass we collapse these into one cluster so the LLM ranks
distinct stories, not duplicates. Two signals:

  1. URL identity — normalise (drop scheme, www., trailing slash, tracking
     query params, fragment) then compare. HN/Reddit "link" posts often point
     at the SAME canonical URL.
  2. Title shingle / token-overlap — when URLs differ (a blog vs an arXiv
     abstract of the same paper), high Jaccard token overlap on the titles
     clusters them.

All hermetic — pure functions over in-memory entry dicts; no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import dedup as _dd  # noqa: E402


# --------------------------------------------------------------------------- #
# URL normalisation                                                           #
# --------------------------------------------------------------------------- #
def test_normalize_url_strips_scheme_www_slash_fragment():
    a = _dd.normalize_url("https://www.example.com/paper/123/")
    b = _dd.normalize_url("http://example.com/paper/123#section")
    assert a == b


def test_normalize_url_drops_tracking_params_keeps_meaningful():
    a = _dd.normalize_url("https://x.com/a?utm_source=hn&utm_medium=feed&id=7")
    b = _dd.normalize_url("https://x.com/a?id=7")
    assert a == b
    # a purely-tracking query collapses to the bare path
    c = _dd.normalize_url("https://x.com/a?utm_campaign=foo")
    assert c == _dd.normalize_url("https://x.com/a")


def test_normalize_url_empty_is_empty():
    assert _dd.normalize_url("") == ""
    assert _dd.normalize_url(None) == ""


# --------------------------------------------------------------------------- #
# title token similarity                                                      #
# --------------------------------------------------------------------------- #
def test_title_similarity_high_for_paraphrase():
    s = _dd.title_similarity(
        "Llama 3 405B open-weights model released by Meta",
        "Meta releases Llama 3 405B open weights model",
    )
    assert s >= 0.6


def test_title_similarity_low_for_unrelated():
    s = _dd.title_similarity(
        "A new vLLM throughput benchmark",
        "Diffusion models for protein folding",
    )
    assert s < 0.3


def test_title_similarity_ignores_stopwords_and_case():
    s = _dd.title_similarity(
        "The Release of GPT-5 by OpenAI",
        "release gpt-5 openai",
    )
    assert s >= 0.6


# --------------------------------------------------------------------------- #
# clustering                                                                  #
# --------------------------------------------------------------------------- #
def _entry(title, link, source, cat="research"):
    return {"title": title, "link": link, "source": source, "category": cat,
            "summary_excerpt": title}


def test_cluster_collapses_same_url_across_sources():
    arxiv = _entry("Cool Paper", "https://arxiv.org/abs/2401.0001", "arxiv-cs-AI")
    hn = _entry("Cool Paper (arxiv.org)", "http://arxiv.org/abs/2401.0001/",
                "hacker-news-frontpage", "community")
    clusters = _dd.cluster_entries([arxiv, hn])
    assert len(clusters) == 1
    c = clusters[0]
    assert len(c.entries) == 2
    assert {"arxiv-cs-AI", "hacker-news-frontpage"} == set(c.sources)


def test_cluster_collapses_paraphrased_titles_diff_url():
    a = _entry("Llama 3 405B open weights released by Meta",
               "https://ai.meta.com/blog/llama3", "huggingface-blog", "blog")
    b = _entry("Meta releases Llama 3 405B open-weights model",
               "https://www.reddit.com/r/LocalLLaMA/x", "r-LocalLLaMA-top",
               "community")
    clusters = _dd.cluster_entries([a, b], title_threshold=0.6)
    assert len(clusters) == 1
    assert len(clusters[0].entries) == 2


def test_cluster_keeps_distinct_stories_separate():
    a = _entry("vLLM throughput benchmark", "https://x.com/1", "hn", "community")
    b = _entry("Protein folding diffusion model", "https://y.com/2", "arxiv",
               "research")
    clusters = _dd.cluster_entries([a, b])
    assert len(clusters) == 2


def test_cluster_representative_is_first_seen():
    a = _entry("Cool Paper", "https://arxiv.org/abs/1", "arxiv-cs-AI")
    b = _entry("Cool Paper discussion", "https://arxiv.org/abs/1",
               "hacker-news-frontpage", "community")
    [cluster] = _dd.cluster_entries([a, b])
    # the representative entry is the first one encountered
    assert cluster.representative["source"] == "arxiv-cs-AI"
    assert cluster.size == 2


def test_dedup_entries_returns_one_representative_per_cluster():
    a = _entry("Cool Paper", "https://arxiv.org/abs/1", "arxiv-cs-AI")
    b = _entry("Cool Paper (arxiv)", "https://arxiv.org/abs/1",
               "hacker-news-frontpage", "community")
    c = _entry("Unrelated story", "https://z.com/q", "simonwillison-blog", "blog")
    deduped = _dd.dedup_entries([a, b, c])
    assert len(deduped) == 2
    # cross-source count is annotated onto the representative
    by_title = {e["title"]: e for e in deduped}
    rep = by_title["Cool Paper"]
    assert rep["cluster_size"] == 2
    assert set(rep["cluster_sources"]) == {"arxiv-cs-AI", "hacker-news-frontpage"}


def test_dedup_empty_input():
    assert _dd.dedup_entries([]) == []
    assert _dd.cluster_entries([]) == []


# --------------------------------------------------------------------------- #
# integration: weekly blob shrinks after dedup                               #
# --------------------------------------------------------------------------- #
def test_integration_weekly_dedups_before_blob(monkeypatch):
    """The weekly collector dedups cross-source duplicates before building the
    LLM blob, so the same story appears once."""
    from phantom_ai_feed import weekly as _weekly

    def _e(title, link, source, cat, excerpt):
        return {"title": title, "link": link, "source": source,
                "category": cat, "summary_excerpt": excerpt}

    entries = [
        _e("Llama 3 405B open weights released by Meta",
           "https://ai.meta.com/blog/llama3", "huggingface-blog", "blog",
           "Meta dropped the 405B checkpoint."),
        _e("Meta releases Llama 3 405B open-weights model",
           "https://ai.meta.com/blog/llama3?utm_source=hn",
           "hacker-news-frontpage", "community",
           "discussion thread on the release"),
        _e("Unrelated: new tokenizer benchmark",
           "https://x.com/tok", "arxiv-cs-CL", "research",
           "a benchmark for tokenizers"),
    ]
    deduped = _dd.dedup_entries(entries)
    # only 2 distinct stories survive dedup (the two Llama posts collapse)
    assert len(deduped) == 2
    blob = _weekly._build_blob(deduped)
    # the Llama story's title appears exactly once in the blob
    assert blob.count("Llama 3 405B") == 1
    assert "tokenizer benchmark" in blob
