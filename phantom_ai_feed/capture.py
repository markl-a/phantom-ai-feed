"""FTS5 capture adapter — fold a digest entry into the phantom knowledge base.

This is the local-first capture seam: each AI-news entry is written into
phantom's SQLite FTS5 store via the ``phantom event capture`` CLI, so the
weekly digest / interview generator can later recall the week's stories with
full-text search. Nothing leaves the machine; the CLI writes to the local
``~/.phantom-mesh/phantom.db``.

Why a CLI seam (not a direct sqlite write): phantom owns the schema, the
at-rest encryption (EventKey), and the FTS5 triggers — re-implementing that
here would drift. The adapter therefore shells out to the binary that already
owns the store, and degrades gracefully when the binary is absent.

Design (mirrors summarize.py's phantom-exec adapter):
  - ``build_capture_command(entry)`` — pure: fold {title, summary, link,
    source} into one ≤2000-char blob and return the argv. No I/O. This is what
    ``dry_run`` returns for inspection.
  - ``capture_entry(entry, *, dry_run=False)`` — the 3-branch executor:
      * no ``phantom`` on PATH        → CaptureResult(status="no-cli")
      * ``phantom`` present but fails → CaptureResult(status="error", detail=…)
      * ``phantom`` present and ok    → CaptureResult(status="ok")
    With ``dry_run=True`` it BUILDS the command and returns it WITHOUT executing.
  - ``capture_many(entries)`` — map ``capture_entry`` over a batch.

The ``ai-feed`` kind is custom: ``phantom recall --kind`` only filters the
built-in kinds (food|focus|habit|text), so retrieve these via full-text
``phantom recall "<query>"`` instead of a kind filter.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

# How long to wait on a single capture before treating it as a failure.
CAPTURE_TIMEOUT_S = 5
# Cap the folded blob so one capture stays bounded (phantom stores the full
# text; we keep it short to stay snappy and avoid pathological feed bodies).
MAX_BLOB_CHARS = 2000

Status = Literal["ok", "error", "no-cli", "dry-run"]


@dataclass
class CaptureResult:
    """Outcome of one capture attempt.

    ``ok`` is True for a successful capture OR a dry-run (the build succeeded
    and there was nothing to execute); False for ``no-cli`` / ``error``.
    """

    status: Status
    detail: Optional[str] = None
    command: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "dry-run")


def _fold_text(entry: dict) -> str:
    """Fold the entry's fields into a single searchable text blob (≤2000 chars).

    ``source`` is always annotated (defaulting to ``phantom-ai-feed``) so every
    captured row is attributable; empty title/summary/link fields are dropped.
    """
    source = (entry.get("source") or "").strip() or "phantom-ai-feed"
    # Prefer an LLM ``summary`` (digest path) but fall back to the raw
    # ``summary_excerpt`` (accumulation path feeds entries straight from fetch)
    # so FTS5 always indexes the body text, not just the title.
    body = (entry.get("summary") or entry.get("summary_excerpt") or "").strip()
    parts = [
        (entry.get("title") or "").strip(),
        body,
        (entry.get("link") or "").strip(),
        f"source: {source}",
    ]
    return "\n".join(p for p in parts if p)[:MAX_BLOB_CHARS]


def build_capture_command(entry: dict) -> list[str]:
    """Build the ``phantom event capture`` argv for ``entry``. Pure — no I/O.

    Flags verified against phantom 0.6.0-rc.1: ``--kind <k> --text <body>``.
    The ``ai-feed`` kind is custom (see module docstring).
    """
    return [
        "phantom",
        "event",
        "capture",
        "--kind",
        "ai-feed",
        "--text",
        _fold_text(entry),
    ]


def capture_entry(
    entry: dict,
    *,
    dry_run: bool = False,
    backend: str = "local",
    db_path=None,
) -> CaptureResult:
    """Capture one entry into the knowledge store.

    ``backend="local"`` (default) writes directly to the pure-stdlib SQLite FTS5
    store (no daemon — see ``store.py``). ``backend="phantom"`` uses the mesh
    ``phantom event capture`` CLI seam (needs ``phantom serve`` running).

    ``dry_run`` builds the phantom command and returns it WITHOUT writing
    anything, regardless of backend.
    """
    if dry_run:
        return CaptureResult(status="dry-run", command=build_capture_command(entry))
    if backend == "phantom":
        return _capture_phantom(entry)
    return _capture_local(entry, db_path)


def _capture_local(entry: dict, db_path) -> CaptureResult:
    """Write the entry into the local SQLite FTS5 store. No daemon required."""
    from . import store

    try:
        store.capture(entry, db_path=db_path or store.DEFAULT_DB)
    except Exception as e:  # disk/DB error — surface, never raise into the run
        return CaptureResult(status="error", detail=str(e)[:200])
    return CaptureResult(status="ok")


def _capture_phantom(entry: dict) -> CaptureResult:
    """Capture via the ``phantom event capture`` CLI (the mesh daemon backend).

    Branches: no ``phantom`` on PATH → ``no-cli``; CLI raised / non-zero /
    timed-out → ``error``; exit 0 → ``ok``.
    """
    cmd = build_capture_command(entry)

    if not shutil.which("phantom"):
        return CaptureResult(
            status="no-cli", detail="phantom not on PATH", command=cmd
        )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=CAPTURE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CaptureResult(
            status="error", detail="capture timed out", command=cmd
        )
    except (OSError, subprocess.SubprocessError) as e:
        return CaptureResult(status="error", detail=str(e)[:200], command=cmd)

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[:200] or "phantom event capture failed"
        return CaptureResult(status="error", detail=detail, command=cmd)

    return CaptureResult(status="ok", command=cmd)


def capture_many(
    entries: Iterable[dict], *, dry_run: bool = False, backend: str = "local", db_path=None
) -> list[CaptureResult]:
    """Capture a batch of entries; per-entry result is collected, never raised."""
    return [
        capture_entry(e, dry_run=dry_run, backend=backend, db_path=db_path)
        for e in entries
    ]
