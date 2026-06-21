"""YouTube channel-id resolver — stdlib only, best-effort.

Turns a human ``@handle`` into the stable ``UC...`` channel id, and the channel
id into its public Atom feed URL — so a feeds.toml can list ``@handle`` (durable)
instead of an opaque ``channel_id`` (which nobody can eyeball or audit).

It reuses the package's hardened network layer (``fetch._http_get``) for
retry/backoff, User-Agent, and the ``PHANTOM_AI_FEED_OFFLINE`` short-circuit —
so this module never opens its own socket and tests patch the SAME seam
(``fetch._raw_http_get``) the rest of the suite already uses.
"""
from __future__ import annotations

import argparse
import re
import sys

from phantom_ai_feed.resolvers import _net

# The page embeds the canonical channel id twice; we try the JSON blob first
# (present on virtually every channel page) and fall back to the <link rel=
# "canonical"> tag. Channel ids are always ``UC`` + URL-safe base64-ish chars.
_EXTERNAL_ID_RE = re.compile(r'"externalId":"(UC[\w-]+)"')
# Loosened: optional scheme (http/https), optional www, and no requirement on
# the closing ``">`` (a trailing attribute or single/double quote may follow).
_CANONICAL_RE = re.compile(
    r'href="https?://(?:www\.)?youtube\.com/channel/(UC[\w-]+)'
)


def channel_feed_url(channel_id: str) -> str:
    """The public Atom feed URL for a YouTube channel id."""
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def _normalize_handle(handle: str) -> str:
    """Strip surrounding whitespace and a single leading ``@``, then casefold.

    YouTube ``@handles`` are case-INSENSITIVE, so ``@AndrejKarpathy`` and
    ``@andrejkarpathy`` are the same channel. Casefolding here means they share
    one cache key (one fetch) and resolve identically; the fetch URL uses the
    casefolded handle too (YouTube treats it case-insensitively).
    """
    return handle.strip().lstrip("@").strip().casefold()


def resolve_channel_id(handle: str, *, cache: dict | None = None) -> str | None:
    """Resolve a YouTube ``@handle`` to its ``UC...`` channel id (or ``None``).

    Best-effort: a network failure returns ``None`` rather than raising, so a
    single dead handle never aborts a batch resolve.

    When ``cache`` is supplied it is a ``{handle: channel_id}`` mapping keyed by
    the NORMALISED handle (no ``@``): a hit returns immediately WITHOUT any
    network call, and a miss that resolves stores the result back for reuse.
    """
    norm = _normalize_handle(handle)
    if cache is not None and norm in cache:
        return cache[norm]

    url = f"https://www.youtube.com/@{norm}"
    raw = _net.get_bytes(url)
    if raw is None:
        return None

    text = raw.decode("utf-8", errors="replace")
    m = _EXTERNAL_ID_RE.search(text) or _CANONICAL_RE.search(text)
    if not m:
        return None

    ucid = m.group(1)
    if cache is not None:
        cache[norm] = ucid
    return ucid


def main(argv: list[str] | None = None) -> int:
    """CLI: resolve each ``@handle`` and print its feed URL to stdout.

    Unresolved handles are skipped with a note on stderr. The exit code is 0
    when AT LEAST ONE handle resolved, and 1 when none did — consistent with the
    podcast/discover CLIs, so the command is usable in a ``&&`` chain.
    """
    parser = argparse.ArgumentParser(
        prog="python -m phantom_ai_feed.resolvers.youtube",
        description="Resolve YouTube @handles to channel feed URLs.",
    )
    parser.add_argument(
        "handles",
        nargs="+",
        metavar="@handle",
        help="one or more YouTube handles (leading @ optional)",
    )
    args = parser.parse_args(argv)

    cache: dict = {}
    resolved_any = False
    for handle in args.handles:
        ucid = resolve_channel_id(handle, cache=cache)
        if ucid is None:
            print(f"could not resolve: {handle}", file=sys.stderr)
            continue
        resolved_any = True
        print(channel_feed_url(ucid))
    return 0 if resolved_any else 1


if __name__ == "__main__":
    sys.exit(main())
