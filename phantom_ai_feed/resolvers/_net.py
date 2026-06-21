"""Shared network helper for the resolver modules — stdlib only.

Every resolver (youtube / podcast / discover) needs the SAME best-effort
"fetch the bytes, or None on any transport failure" behaviour around the
package's hardened ``fetch._http_get`` (retry/backoff/User-Agent/offline). This
collapses the three near-identical ``try/except`` blocks into one home so the
swallowed-error set cannot drift between resolvers.

``get_bytes`` returns the body on success and ``None`` on the transport error
types the resolvers treat as "not there / unreachable" — exactly the set the
old per-module wrappers caught: ``urllib.error.URLError`` (covers ``HTTPError``,
e.g. a 404 probe), ``OSError``, and ``TimeoutError``.
"""
from __future__ import annotations

import urllib.error

from phantom_ai_feed import fetch as _fetch


def get_bytes(url: str, *, max_retries: int | None = None) -> bytes | None:
    """Fetch ``url`` and return its bytes, or ``None`` on any transport failure.

    Delegates to ``fetch._http_get`` (shared retry/backoff/UA/offline). When
    ``max_retries`` is given it overrides the default retry budget — e.g. the
    discover probe passes ``max_retries=0`` so each speculative candidate is a
    single attempt (no per-candidate backoff amplification). On
    ``URLError`` / ``OSError`` / ``TimeoutError`` it returns ``None`` rather than
    raising, so a single dead URL never aborts a batch.
    """
    try:
        if max_retries is None:
            return _fetch._http_get(url)
        return _fetch._http_get(url, max_retries=max_retries)
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
