"""Podcast RSS resolver — turn an Apple Podcasts id (or search term) into the
show's RSS ``feedUrl`` via the public iTunes lookup/search API. Pure stdlib.

Reuses ``phantom_ai_feed.fetch`` for the network layer (retry/backoff/UA/offline)
so this resolver never opens its own socket — ``_fetch._http_get`` is the single
seam, patched out in the offline unit tests.

The iTunes endpoints used:
  * lookup:  https://itunes.apple.com/lookup?id=<apple_id>&entity=podcast
  * search:  https://itunes.apple.com/search?term=<quoted>&entity=podcast&limit=1

Both return JSON ``{"resultCount": N, "results": [{..., "feedUrl": "..."}]}``;
we return the first non-empty ``feedUrl`` (or ``None`` if there is none).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from urllib.parse import quote

from phantom_ai_feed import fetch as _fetch

_LOOKUP_URL = "https://itunes.apple.com/lookup?id={id}&entity=podcast"
_SEARCH_URL = "https://itunes.apple.com/search?term={term}&entity=podcast&limit=1"


def resolve_feed(
    *, apple_id: str | int | None = None, term: str | None = None
) -> str | None:
    """Resolve a podcast RSS ``feedUrl`` from an Apple id or a search term.

    Exactly one of ``apple_id`` / ``term`` drives the request:
      * ``apple_id`` -> iTunes *lookup* (exact, single show).
      * ``term``     -> iTunes *search* (best match, ``limit=1``).

    Returns the first non-empty ``feedUrl`` in the results, or ``None`` when
    there are no results / none carry a ``feedUrl``. JSON-decode and network
    failures (URLError/OSError/TimeoutError/JSONDecodeError) are swallowed to
    ``None`` — this is a best-effort lookup, not a hard dependency.

    Passing NEITHER argument is a usage error and RAISES ``ValueError``; that is
    deliberately NOT swallowed (a bug in the caller, not a transient fetch
    failure).
    """
    if apple_id is not None:
        url = _LOOKUP_URL.format(id=apple_id)
    elif term:
        url = _SEARCH_URL.format(term=quote(term))
    else:
        raise ValueError("apple_id or term required")

    try:
        raw = _fetch._http_get(url)
        data = json.loads(raw)
    except (
        urllib.error.URLError,
        OSError,
        TimeoutError,
        json.JSONDecodeError,
        ValueError,
    ):
        # Only network/JSON-decode failures land here. The argument-validation
        # ValueError above is raised BEFORE this try, so it can never be caught.
        return None

    for result in (data.get("results") or []) if isinstance(data, dict) else []:
        feed_url = result.get("feedUrl") if isinstance(result, dict) else None
        if feed_url:
            return feed_url
    return None


def main(argv: list[str] | None = None) -> int:
    """CLI: print the resolved RSS feedUrl to stdout.

    ``python -m phantom_ai_feed.resolvers.podcast --id 1469999563``
    ``python -m phantom_ai_feed.resolvers.podcast --term "Latent Space"``

    Exits non-zero (with a stderr note) when the feed cannot be resolved.
    """
    parser = argparse.ArgumentParser(
        prog="phantom_ai_feed.resolvers.podcast",
        description="Resolve a podcast RSS feedUrl via the iTunes API.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", dest="apple_id", help="Apple Podcasts numeric id")
    group.add_argument("--term", dest="term", help="Search term (show name)")
    args = parser.parse_args(argv)

    feed_url = resolve_feed(apple_id=args.apple_id, term=args.term)
    if not feed_url:
        which = f"id={args.apple_id}" if args.apple_id else f"term={args.term!r}"
        print(f"podcast: could not resolve a feedUrl for {which}", file=sys.stderr)
        return 1
    print(feed_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
