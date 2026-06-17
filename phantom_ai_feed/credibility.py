"""Source credibility weighting for the weekly ranking + dedup tie-breaks.

Not every source is equally trustworthy or equally signal-dense. Curated
research/blog feeds (arXiv, Karpathy, Lilian Weng) carry more per-item signal
than the firehose community feeds (HN front page, r/LocalLLaMA), which are
high-volume and noisy. We fold three transparent factors into ONE score per
entry and use it to (a) order the entries we hand the weekly LLM and (b) break
dedup ties (which source becomes a cluster's representative).

Score factors (each in a bounded range, then combined as a weighted sum so the
result stays interpretable):

  1. **category trust** — a per-category weight; ``research``/``blog`` outrank
     ``community``. Unknown categories get a neutral default.
  2. **fetch-success history** — ``success_ratio`` of a source's recent
     fetches; a source that errors a lot is trusted less. Unseen sources get a
     neutral prior (NOT zero — absence of evidence isn't evidence of failure).
  3. **cross-source corroboration** — ``cluster_size`` from ``dedup``: a story
     independently covered by several sources is more important, so a larger
     cluster lifts the score (with diminishing returns via log).

Everything here is a deliberately simple, auditable heuristic — pure stdlib,
no network, no learned weights. Tune the constants below to taste.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Optional

# Per-category trust weight in (0, 1]. Curated > community; unknown = neutral.
CATEGORY_WEIGHTS: dict[str, float] = {
    "research": 1.0,
    "blog": 0.9,
    "community": 0.6,
    "misc": 0.5,
}
# Neutral default for a category we have no opinion on. Sits at/below the
# curated tiers so an unknown source never out-trusts a known research feed.
NEUTRAL_CATEGORY_WEIGHT = 0.5

# Neutral prior for a source with no fetch history yet (Laplace-ish: assume
# roughly reliable until proven otherwise, but not perfect).
NEUTRAL_SUCCESS_RATIO = 0.7

# How the three factors combine. Category trust dominates; history and
# corroboration are meaningful but secondary nudges.
W_CATEGORY = 1.0
W_HISTORY = 0.5
W_CORROBORATION = 0.4


def category_weight(category: str) -> float:
    """Trust weight for a feed category, defaulting to a neutral prior."""
    return CATEGORY_WEIGHTS.get((category or "").strip().lower(),
                                NEUTRAL_CATEGORY_WEIGHT)


def success_ratio(counts: Optional[Mapping[str, int]]) -> float:
    """ok / (ok + err) for a source, or a neutral prior when unseen/empty."""
    if not counts:
        return NEUTRAL_SUCCESS_RATIO
    ok = int(counts.get("ok", 0))
    err = int(counts.get("err", 0))
    total = ok + err
    if total == 0:
        return NEUTRAL_SUCCESS_RATIO
    return ok / total


def _corroboration_bonus(cluster_size: int) -> float:
    """Diminishing-returns bonus for a story covered by multiple sources.

    size 1 → 0.0, size 2 → ~0.69, size 4 → ~1.10. log keeps a viral story from
    dominating purely on copy count.
    """
    return math.log(max(1, int(cluster_size)))


def score_entry(
    entry: Mapping[str, Any],
    *,
    history: Optional[Mapping[str, Mapping[str, int]]] = None,
) -> float:
    """Combined credibility score for one entry. Higher = more credible.

    ``history`` maps source-name → {"ok": int, "err": int}. When absent, the
    history factor falls back to the neutral prior so scoring still works with
    no history at all.
    """
    cat = category_weight(entry.get("category", ""))
    src = entry.get("source", "")
    src_counts = (history or {}).get(src)
    hist = success_ratio(src_counts)
    corro = _corroboration_bonus(entry.get("cluster_size", 1) or 1)
    return round(
        W_CATEGORY * cat + W_HISTORY * hist + W_CORROBORATION * corro, 6
    )


def rank_entries(
    entries: Iterable[Mapping[str, Any]],
    *,
    history: Optional[Mapping[str, Mapping[str, int]]] = None,
) -> list[dict]:
    """Return entries ordered most-credible first, each annotated with
    ``credibility``. Stable for equal scores (input order preserved)."""
    scored = []
    for idx, e in enumerate(entries):
        d = dict(e)
        d["credibility"] = score_entry(e, history=history)
        scored.append((idx, d))
    # sort by score desc, then original index asc (stable tie-break)
    scored.sort(key=lambda t: (-t[1]["credibility"], t[0]))
    return [d for _i, d in scored]


def pick_representative(
    representative: Mapping[str, Any],
    members: Iterable[Mapping[str, Any]],
    *,
    history: Optional[Mapping[str, Mapping[str, int]]] = None,
) -> dict:
    """Choose the most-credible member of a dedup cluster as its representative.

    ``members`` is the raw set of entries that collapsed into the cluster (the
    cross-source duplicates). The cluster-level annotations from the existing
    representative (``cluster_size`` / ``cluster_sources``) are carried over so
    the corroboration signal survives the re-pick. Ties keep the first member
    (input order = source priority).
    """
    members = list(members)
    if not members:
        return dict(representative)

    def _sized(m: Mapping[str, Any]) -> dict:
        d = dict(m)
        # carry cluster-level annotations so corroboration is scored uniformly
        d.setdefault("cluster_size", representative.get("cluster_size", 1))
        d.setdefault("cluster_sources",
                     representative.get("cluster_sources", []))
        return d

    best_idx, best_score = 0, float("-inf")
    for idx, m in enumerate(members):
        s = score_entry(_sized(m), history=history)
        if s > best_score:
            best_idx, best_score = idx, s

    chosen = _sized(members[best_idx])
    chosen["credibility"] = round(best_score, 6)
    return chosen


def build_fetch_history(
    results: Iterable[tuple[Mapping[str, Any], Any]],
) -> dict[str, dict[str, int]]:
    """Turn ``fetch.fetch_all``-style ``[(feed, entries|Exception), ...]``
    results into a ``{source_name: {"ok": int, "err": int}}`` history map.

    An Exception payload counts as an error; anything else (a list of entries,
    even empty) counts as a successful fetch.
    """
    hist: dict[str, dict[str, int]] = {}
    for feed, payload in results:
        name = feed.get("name", feed.get("url", "unknown"))
        bucket = hist.setdefault(name, {"ok": 0, "err": 0})
        if isinstance(payload, Exception):
            bucket["err"] += 1
        else:
            bucket["ok"] += 1
    return hist
