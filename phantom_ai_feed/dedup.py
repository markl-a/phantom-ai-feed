"""Cross-source dedup / topic clustering.

A single story routinely shows up across arXiv, Reddit (r/LocalLLaMA), and
Hacker News in the same week. If we hand all of them to the weekly ranking
pass, the LLM wastes its budget ranking the same story three times and the
digest reads as repetitive. This module collapses duplicates into clusters
BEFORE ranking, keeping one representative entry per real story while
remembering how many sources covered it (a useful credibility/heat signal,
consumed by ``credibility.py`` for tie-breaks).

Two signals, OR-combined:

1. **URL identity** — ``normalize_url`` strips scheme, ``www.``, a trailing
   slash, the fragment, and tracking query params (``utm_*``, ``fbclid``,
   ``ref``, …). HN/Reddit link posts usually point at the SAME canonical URL
   as the primary source, so this catches the common case exactly.

2. **Title token overlap** — when the URLs differ (a vendor blog vs an arXiv
   abstract vs a Reddit thread about the same paper), a high token-Jaccard on
   the de-stopworded, normalised titles clusters them. Threshold is tunable;
   the default (0.6) is deliberately conservative to avoid over-merging.

Pure stdlib, no network — operates on the in-memory entry dicts produced by
``fetch``. Clustering is single-link agglomerative via a tiny union-find,
which is O(n²) on the (small, ≤ a few hundred) weekly entry set.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import parse_qsl, urlsplit, urlunsplit

_WORD = re.compile(r"\w+")

# Query keys that carry no story identity — pure tracking / referral noise.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = frozenset(
    {"fbclid", "gclid", "ref", "ref_src", "ref_url", "source",
     "mc_cid", "mc_eid", "igshid", "spm", "_hsenc", "_hsmi"}
)

# Common English + feed-boilerplate stopwords dropped before title comparison,
# so "Meta releases X" and "The release of X by Meta" still match on content
# words. Kept small and transparent on purpose.
_STOPWORDS = frozenset(
    {"the", "a", "an", "of", "by", "for", "to", "in", "on", "and", "or",
     "with", "is", "are", "as", "at", "from", "new", "release", "released",
     "releases", "announces", "announced", "introducing", "introduces",
     "model", "models", "via", "using", "show", "hn"}
)

# Token threshold above which two titles are considered the same story.
DEFAULT_TITLE_THRESHOLD = 0.6


def normalize_url(url: str | None) -> str:
    """Canonicalise a URL for identity comparison.

    Drops scheme, leading ``www.``, fragment, and tracking query params; lower-
    cases the host; removes a single trailing slash from the path. Remaining
    meaningful query params are kept and sorted so order does not matter.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()

    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    path = parts.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_key(k)
    ]
    query = "&".join(f"{k}={v}" for k, v in sorted(kept))

    # scheme dropped (http/https treated identically), fragment dropped.
    return urlunsplit(("", host, path, query, "")).lstrip("/") or host


def _is_tracking_key(key: str) -> bool:
    k = key.lower()
    return k in _TRACKING_KEYS or any(k.startswith(p) for p in _TRACKING_PREFIXES)


def _title_tokens(title: str) -> set[str]:
    return {
        t for t in _WORD.findall((title or "").lower())
        if t and t not in _STOPWORDS
    }


def title_similarity(a: str, b: str) -> float:
    """Token-Jaccard similarity of two titles after stopword removal + casefold."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclass
class Cluster:
    """A group of entries believed to be the same underlying story."""

    entries: list[dict] = field(default_factory=list)

    @property
    def representative(self) -> dict:
        """First entry encountered — preserves input order / source priority."""
        return self.entries[0]

    @property
    def size(self) -> int:
        return len(self.entries)

    @property
    def sources(self) -> list[str]:
        """Distinct source names covering this story (insertion order)."""
        seen: list[str] = []
        for e in self.entries:
            s = e.get("source", "")
            if s and s not in seen:
                seen.append(s)
        return seen


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Keep the lower index as the root so the first-seen entry stays
            # the representative.
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            self.parent[hi] = lo


def _same_story(
    a: dict, b: dict, *, title_threshold: float
) -> bool:
    ua, ub = normalize_url(a.get("link")), normalize_url(b.get("link"))
    if ua and ub and ua == ub:
        return True
    return title_similarity(a.get("title", ""), b.get("title", "")) >= title_threshold


def cluster_entries(
    entries: Iterable[dict],
    *,
    title_threshold: float = DEFAULT_TITLE_THRESHOLD,
) -> list[Cluster]:
    """Single-link cluster ``entries`` by URL identity OR title overlap.

    Returns clusters in first-seen order; each cluster's ``representative`` is
    the earliest entry in input order. O(n²) — fine for the weekly set size.
    """
    items = list(entries)
    n = len(items)
    if n == 0:
        return []

    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if _same_story(items[i], items[j], title_threshold=title_threshold):
                uf.union(i, j)

    # Group by root, preserving first-seen order of roots and members.
    groups: dict[int, Cluster] = {}
    order: list[int] = []
    for idx in range(n):
        root = uf.find(idx)
        if root not in groups:
            groups[root] = Cluster()
            order.append(root)
        groups[root].entries.append(items[idx])
    return [groups[r] for r in order]


def dedup_entries(
    entries: Iterable[dict],
    *,
    title_threshold: float = DEFAULT_TITLE_THRESHOLD,
) -> list[dict]:
    """Collapse cross-source duplicates to one representative per story.

    Each returned representative is annotated (a shallow copy, inputs untouched)
    with:
      - ``cluster_size``    — how many raw entries collapsed into it
      - ``cluster_sources`` — the distinct source names that covered the story
    These feed the weekly ranking and the credibility tie-breaks.
    """
    out: list[dict] = []
    for cluster in cluster_entries(entries, title_threshold=title_threshold):
        rep = dict(cluster.representative)
        rep["cluster_size"] = cluster.size
        rep["cluster_sources"] = cluster.sources
        out.append(rep)
    return out
