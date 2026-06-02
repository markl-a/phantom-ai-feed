"""Summarizer: prefers `phantom exec` (mesh provider trait), then Gemini REST, then stub.

Design:
- `summarize_phantom(text, max_words)`         → str via `phantom exec`. Raises on failure.
- `summarize_gemini(text, api_key, max_words)` → str. Raises on transport error.
- `summarize_stub(text, max_words)`            → str. Always succeeds; no LLM.
- `summarize(text, ...)` dispatcher: phantom exec → Gemini → stub; `use_stub=True` forces stub.

Gemini endpoint reference (REST, no SDK):
  POST https://generativelanguage.googleapis.com/v1beta/models/
       gemini-2.5-flash:generateContent?key=<API_KEY>
  body = {"contents":[{"parts":[{"text": <prompt>}]}]}
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Optional

GEMINI_MODEL = os.environ.get("PHANTOM_AI_FEED_GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
TIMEOUT_S = 30
UA = "phantom-ai-feed/0.1"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def summarize_stub(text: str, max_words: int = 120) -> str:
    """Pure-stdlib extractive summary: first 2 sentences, capped at max_words."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return "(no content)"
    parts = _SENTENCE_SPLIT.split(cleaned)
    pick = " ".join(parts[:2]) if parts else cleaned
    words = pick.split()
    if len(words) > max_words:
        pick = " ".join(words[:max_words]) + " …"
    return pick


def _build_prompt(text: str, max_words: int) -> str:
    return (
        "You are an AI engineering news editor for a Chinese-speaking ML "
        "engineer. Summarise the following article in ≤"
        f"{max_words} words, mixing 繁體中文 + key English technical terms. "
        "Focus on: novel idea, concrete numbers, who should care. Output the "
        "summary only, no preamble.\n\nARTICLE:\n" + (text or "").strip()
    )


def summarize_gemini(
    text: str,
    api_key: str,
    max_words: int = 120,
    timeout_s: float = TIMEOUT_S,
) -> str:
    """Call Gemini Flash REST. Raises urllib.error.URLError on network failure."""
    if not api_key:
        raise ValueError("GEMINI_API_KEY required for summarize_gemini")
    payload = {
        "contents": [{"parts": [{"text": _build_prompt(text, max_words)}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": max(256, max_words * 4),
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{GEMINI_ENDPOINT}?key={api_key}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise urllib.error.URLError(f"non-json from gemini: {e}") from e
    # Defensive extraction: {"candidates":[{"content":{"parts":[{"text":...}]}}]}
    try:
        return obj["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise urllib.error.URLError(f"unexpected gemini payload shape: {e}") from e


def summarize_phantom(text: str, max_words: int = 120, timeout_s: float = 60) -> str:
    """Summarise via `phantom exec` — reuses phantom's provider trait (multi-provider
    fallback, cost tracking, unified keys). Raises on missing binary / failure."""
    if not shutil.which("phantom"):
        raise RuntimeError("phantom not on PATH")
    proc = subprocess.run(
        ["phantom", "exec", _build_prompt(text, max_words)],
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:200] or "phantom exec failed")
    out = proc.stdout.strip()
    if not out:
        raise RuntimeError("phantom exec returned empty output")
    return out


def summarize(
    text: str,
    *,
    use_stub: bool = False,
    api_key: Optional[str] = None,
    max_words: int = 120,
    prefer_phantom: bool = True,
) -> str:
    """Dispatcher. Preference order (each degrades gracefully to the next):

    1. ``phantom exec`` — reuse the mesh provider trait (default when phantom is
       on PATH). Keeps fallback / cost tracking / keys inside phantom.
    2. direct Gemini REST — if a GEMINI_API_KEY is available.
    3. stdlib stub — always succeeds.

    ``use_stub=True`` forces the stub regardless (offline / deterministic tests).
    """
    if use_stub:
        return summarize_stub(text, max_words=max_words)

    if prefer_phantom and shutil.which("phantom"):
        try:
            return summarize_phantom(text, max_words=max_words)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            pass  # fall through to Gemini / stub

    key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
    if key:
        try:
            return summarize_gemini(text, key, max_words=max_words)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass

    return summarize_stub(text, max_words=max_words)
