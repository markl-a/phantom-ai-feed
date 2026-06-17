"""P2.3 — source credibility weighting (unit).

Bias the weekly ranking and dedup tie-breaks by how much we trust a source.
Three inputs combine into one score per entry:

  1. per-category trust — research/blog (curated) outrank community (HN/Reddit,
     noisier) by a configurable category weight.
  2. fetch-success history — a source that has been reliably fetchable is
     trusted more than one that frequently errors (success_ratio in [0,1]).
  3. cross-source corroboration — an entry whose dedup cluster spans several
     sources (cluster_size > 1) is more important / more credible.

The score is then used to (a) ORDER entries for the weekly blob (most credible
first) and (b) break dedup ties (keep the most-credible representative).

Pure, hermetic — no network, no files.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import credibility as _cred  # noqa: E402


def _entry(title, source, category, cluster_size=1, cluster_sources=None):
    return {
        "title": title,
        "source": source,
        "category": category,
        "link": f"https://x/{title}",
        "cluster_size": cluster_size,
        "cluster_sources": cluster_sources or [source],
    }


# --------------------------------------------------------------------------- #
# category trust                                                              #
# --------------------------------------------------------------------------- #
def test_category_weight_research_beats_community():
    assert _cred.category_weight("research") > _cred.category_weight("community")
    assert _cred.category_weight("blog") > _cred.category_weight("community")


def test_unknown_category_gets_neutral_default():
    w = _cred.category_weight("totally-unknown-cat")
    assert 0.0 < w <= 1.0
    # neutral default sits at/below a known curated category
    assert w <= _cred.category_weight("research")


# --------------------------------------------------------------------------- #
# fetch-success history                                                       #
# --------------------------------------------------------------------------- #
def test_history_boosts_reliable_source():
    history = {"reliable": {"ok": 10, "err": 0}, "flaky": {"ok": 2, "err": 8}}
    rel = _cred.score_entry(_entry("a", "reliable", "blog"), history=history)
    flaky = _cred.score_entry(_entry("b", "flaky", "blog"), history=history)
    assert rel > flaky


def test_missing_history_is_neutral_not_zero():
    # an unseen source must not be punished to 0 — it gets a neutral prior.
    s = _cred.score_entry(_entry("a", "brand-new", "blog"), history={})
    assert s > 0.0


def test_success_ratio_computed():
    assert _cred.success_ratio({"ok": 3, "err": 1}) == 0.75
    # unseen → neutral prior (not 0, not 1)
    r = _cred.success_ratio(None)
    assert 0.0 < r < 1.0


# --------------------------------------------------------------------------- #
# cross-source corroboration                                                  #
# --------------------------------------------------------------------------- #
def test_more_sources_raises_score():
    one = _cred.score_entry(_entry("a", "hn", "community", cluster_size=1))
    three = _cred.score_entry(
        _entry("a", "hn", "community", cluster_size=3,
               cluster_sources=["hn", "arxiv-cs-AI", "r-LocalLLaMA-top"])
    )
    assert three > one


# --------------------------------------------------------------------------- #
# ranking                                                                     #
# --------------------------------------------------------------------------- #
def test_rank_entries_orders_by_credibility_desc():
    entries = [
        _entry("community-single", "hn", "community", cluster_size=1),
        _entry("research-corroborated", "arxiv-cs-AI", "research",
               cluster_size=3,
               cluster_sources=["arxiv-cs-AI", "hn", "r-LocalLLaMA-top"]),
        _entry("blog-single", "karpathy-blog", "blog", cluster_size=1),
    ]
    ranked = _cred.rank_entries(entries)
    titles = [e["title"] for e in ranked]
    # the corroborated research item ranks first; community single last
    assert titles[0] == "research-corroborated"
    assert titles[-1] == "community-single"
    # score is annotated onto each entry
    assert all("credibility" in e for e in ranked)
    # scores are non-increasing
    scores = [e["credibility"] for e in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_is_stable_for_equal_scores():
    a = _entry("a", "hn", "community")
    b = _entry("b", "hn", "community")
    ranked = _cred.rank_entries([a, b])
    assert [e["title"] for e in ranked] == ["a", "b"]


# --------------------------------------------------------------------------- #
# dedup tie-break integration                                                 #
# --------------------------------------------------------------------------- #
def test_dedup_tiebreak_keeps_most_credible_representative():
    """When two sources cover the same story, the more credible source becomes
    the representative after a credibility-aware re-pick."""
    from phantom_ai_feed import dedup as _dd

    community = {"title": "Llama 3 405B released by Meta",
                 "link": "https://ai.meta.com/llama3",
                 "source": "hacker-news-frontpage", "category": "community",
                 "summary_excerpt": "x"}
    research = {"title": "Meta releases Llama 3 405B model",
                "link": "https://ai.meta.com/llama3?utm_source=hn",
                "source": "arxiv-cs-AI", "category": "research",
                "summary_excerpt": "y"}
    # community listed first, so naive dedup would keep it as representative.
    deduped = _dd.dedup_entries([community, research])
    assert len(deduped) == 1
    # credibility-aware re-pick promotes the research source.
    best = _cred.pick_representative(deduped[0], [community, research])
    assert best["source"] == "arxiv-cs-AI"


def test_integration_weekly_ranks_credible_sources_first(monkeypatch):
    """The weekly collector orders entries most-credible-first: a research feed
    that errored is excluded; a community single-source story sinks below a
    corroborated research story in the blob handed to the LLM."""
    from phantom_ai_feed import weekly as _weekly
    from phantom_ai_feed import fetch as _fetch

    feeds = [
        {"name": "arxiv-cs-AI", "url": "u1", "category": "research"},
        {"name": "hacker-news-frontpage", "url": "u2", "category": "community"},
    ]

    def fake_load(_path):
        return feeds

    def fake_fetch_all(_feeds, top_n=3):
        return [
            (feeds[0], [{"title": "Transformer scaling law paper",
                         "link": "https://arxiv.org/abs/1",
                         "source": "arxiv-cs-AI", "category": "research",
                         "summary_excerpt": "x"}]),
            (feeds[1], [{"title": "Funny meme about GPUs",
                         "link": "https://news.ycombinator.com/2",
                         "source": "hacker-news-frontpage",
                         "category": "community", "summary_excerpt": "y"}]),
        ]

    monkeypatch.setattr(_fetch, "load_feeds", fake_load)
    monkeypatch.setattr(_fetch, "fetch_all", fake_fetch_all)

    entries, ok, total = _weekly._collect_items(Path("ignored.toml"), top_n=3)
    assert ok == 2 and total == 2
    # research entry ranked above the community one
    assert entries[0]["source"] == "arxiv-cs-AI"
    assert entries[-1]["source"] == "hacker-news-frontpage"
    blob = _weekly._build_blob(entries)
    assert blob.index("Transformer scaling law") < blob.index("Funny meme")


def test_build_fetch_history_from_results():
    """A helper turns fetch_all-style results into the {source: {ok,err}} map."""
    results = [
        ({"name": "good"}, [{"title": "t"}]),       # ok
        ({"name": "good"}, [{"title": "u"}]),       # ok again
        ({"name": "bad"}, RuntimeError("boom")),    # error
    ]
    hist = _cred.build_fetch_history(results)
    assert hist["good"]["ok"] == 2
    assert hist["bad"]["err"] == 1
    assert _cred.success_ratio(hist["good"]) == 1.0
