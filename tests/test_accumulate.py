"""accumulate.run — the first-class FTS5 accumulation path.

Ties conditional fetch -> capture: changed feeds (HTTP 200) have their entries
captured into the phantom FTS5 store; unchanged feeds (HTTP 304 -> NotModified)
are skipped without re-capture; errored feeds are counted and skipped. The
validator cache is loaded before and saved after the run so the NEXT run can ask
"changed since last time?".

Hermetic: ``fetch_all`` and the capture seam are patched; no sockets, no CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phantom_ai_feed import accumulate as _accum  # noqa: E402
from phantom_ai_feed import capture as _capture  # noqa: E402
from phantom_ai_feed import dedup as _dedup  # noqa: E402
from phantom_ai_feed import fetch as _fetch  # noqa: E402


def _ok(captured=None):
    def _cap(entry, dry_run=False):
        if captured is not None:
            captured.append(entry)
        return _capture.CaptureResult(status="dry-run" if dry_run else "ok")
    return _cap


def _entry(title, excerpt="body text", source="src"):
    return {
        "title": title,
        "link": f"https://e/{title}",
        "summary_excerpt": excerpt,
        "source": source,
        "category": "research",
    }


def _patch_feeds(monkeypatch, results):
    """Patch load_feeds + fetch_all so accumulate sees ``results`` (a list of
    (feed, payload) pairs, payload = list[entry] | NotModified | Exception)."""
    feeds = [feed for feed, _ in results]
    monkeypatch.setattr(_accum._fetch, "load_feeds", lambda _p: feeds)
    monkeypatch.setattr(
        _accum._fetch, "fetch_all", lambda f, top_n=3, cache=None: results
    )


def test_accumulate_captures_changed_feed_entries(monkeypatch, tmp_path):
    captured: list[dict] = []
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: (
            captured.append(entry) or _capture.CaptureResult(status="ok")
        ),
    )
    feed = {"name": "f", "url": "https://e/f"}
    _patch_feeds(monkeypatch, [(feed, [_entry("a"), _entry("b")])])

    res = _accum.run(Path("ignored.toml"), cache_path=tmp_path / "c.json")

    assert res.changed == 1
    assert res.unchanged == 0
    assert res.errored == 0
    assert res.captured == 2
    assert [e["title"] for e in captured] == ["a", "b"]


def test_accumulate_skips_unchanged_feed(monkeypatch, tmp_path):
    """A 304 feed (NotModified payload) captures nothing and counts as unchanged."""
    calls = {"n": 0}
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: (
            calls.update(n=calls["n"] + 1) or _capture.CaptureResult(status="ok")
        ),
    )
    feed = {"name": "f", "url": "https://e/f"}
    _patch_feeds(monkeypatch, [(feed, _fetch.NotModified())])

    res = _accum.run(Path("ignored.toml"), cache_path=tmp_path / "c.json")

    assert res.unchanged == 1
    assert res.changed == 0
    assert res.captured == 0
    assert calls["n"] == 0  # capture never attempted for an unchanged feed


def test_accumulate_counts_errored_feed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: _capture.CaptureResult(status="ok"),
    )
    feed = {"name": "bad", "url": "https://e/bad"}
    _patch_feeds(monkeypatch, [(feed, OSError("boom"))])

    res = _accum.run(Path("ignored.toml"), cache_path=tmp_path / "c.json")

    assert res.errored == 1
    assert res.changed == 0
    assert res.captured == 0


def test_accumulate_passes_raw_entry_with_excerpt_to_capture(monkeypatch, tmp_path):
    """The accumulation path hands the raw fetched entry (carrying
    ``summary_excerpt``) straight to capture — the summary/excerpt impedance is
    resolved at the capture seam (see test_fold_text_falls_back_to_excerpt), not
    band-aided per-caller here."""
    seen: list[dict] = []
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: (
            seen.append(entry) or _capture.CaptureResult(status="ok")
        ),
    )
    feed = {"name": "f", "url": "https://e/f"}
    _patch_feeds(monkeypatch, [(feed, [_entry("a", excerpt="novel KV-cache trick")])])

    _accum.run(Path("ignored.toml"), cache_path=tmp_path / "c.json")

    assert seen[0].get("summary_excerpt") == "novel KV-cache trick"


def test_fold_text_falls_back_to_excerpt(monkeypatch):
    """capture._fold_text must search the excerpt when a raw fetched entry has
    only ``summary_excerpt`` and no ``summary`` — otherwise FTS5 rows carry only
    the title."""
    cmd = _capture.build_capture_command(
        {"title": "T", "summary_excerpt": "body via excerpt", "link": "L", "source": "s"}
    )
    text = cmd[cmd.index("--text") + 1]
    assert "body via excerpt" in text


def test_accumulate_dry_run_writes_nothing_and_skips_cache(monkeypatch, tmp_path):
    """--dry-run must not count anything as captured (nothing is written) and
    must NOT persist the validator cache (else a later real run would 304-skip
    feeds whose entries were never actually captured)."""
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: _capture.CaptureResult(
            status="dry-run" if dry_run else "ok"
        ),
    )
    feed = {"name": "f", "url": "https://e/f"}
    _patch_feeds(monkeypatch, [(feed, [_entry("a"), _entry("b")])])
    cache_path = tmp_path / "c.json"

    res = _accum.run(Path("ignored.toml"), cache_path=cache_path, dry_run=True)

    assert res.changed == 1
    assert res.captured == 0          # dry-run wrote nothing -> not "captured"
    assert res.capture_failed == 0    # dry-run is not a failure either
    assert not cache_path.exists()    # dry-run must not poison the cache


def test_accumulate_reverts_validator_when_capture_fails(monkeypatch, tmp_path):
    """If a changed feed's entries fail to capture, its refreshed validator must
    NOT be persisted — otherwise next run's 304 would skip entries that never
    reached FTS5 (silent data loss)."""
    cache_path = tmp_path / "c.json"

    def fake_fetch_all(feeds, top_n=3, cache=None):
        cache["https://e/f"] = {"etag": '"fresh"', "last_modified": "Sat, 06"}
        return [({"name": "f", "url": "https://e/f"}, [_entry("a")])]

    monkeypatch.setattr(_accum._fetch, "load_feeds", lambda _p: [{"url": "https://e/f"}])
    monkeypatch.setattr(_accum._fetch, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: _capture.CaptureResult(status="no-cli"),
    )

    res = _accum.run(Path("ignored.toml"), cache_path=cache_path)

    assert res.capture_failed == 1
    assert res.captured == 0
    # validator reverted (prior was empty -> absent) so next run re-fetches it
    assert "https://e/f" not in _fetch.load_feed_cache(cache_path)


def test_accumulate_persists_validator_cache(monkeypatch, tmp_path):
    """The cache fetch_all mutated must be written back for the next run."""
    cache_path = tmp_path / "fetch-cache.json"

    def fake_fetch_all(feeds, top_n=3, cache=None):
        # Simulate a 200 that refreshed a validator into the shared cache.
        cache["https://e/f"] = {"etag": '"v9"', "last_modified": "Sat, 06"}
        return [({"name": "f", "url": "https://e/f"}, [_entry("a")])]

    monkeypatch.setattr(_accum._fetch, "load_feeds", lambda _p: [{"url": "https://e/f"}])
    monkeypatch.setattr(_accum._fetch, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: _capture.CaptureResult(status="ok"),
    )

    _accum.run(Path("ignored.toml"), cache_path=cache_path)

    assert _fetch.load_feed_cache(cache_path) == {
        "https://e/f": {"etag": '"v9"', "last_modified": "Sat, 06"}
    }


def test_accumulate_counts_capture_failure(monkeypatch, tmp_path):
    """A capture that fails (e.g. no phantom CLI) is counted, not silently lost."""
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: _capture.CaptureResult(
            status="no-cli", detail="phantom not on PATH"
        ),
    )
    feed = {"name": "f", "url": "https://e/f"}
    _patch_feeds(monkeypatch, [(feed, [_entry("a"), _entry("b")])])

    res = _accum.run(Path("ignored.toml"), cache_path=tmp_path / "c.json")

    assert res.changed == 1
    assert res.captured == 0
    assert res.capture_failed == 2


# --------------------------------------------------------------------------- #
# ② entry-level dedup (per-feed persistent seen-store)                         #
# --------------------------------------------------------------------------- #
def test_accumulate_skips_already_seen_entry(monkeypatch, tmp_path):
    """An entry whose key is already in the feed's seen-store is not re-captured."""
    seen_path = tmp_path / "seen.json"
    feed = {"name": "f", "url": "https://e/f"}
    _fetch.save_feed_cache(seen_path, {"https://e/f": [_dedup.entry_key(_entry("a"))]})

    captured: list[dict] = []
    monkeypatch.setattr(_accum._capture, "capture_entry", _ok(captured))
    _patch_feeds(monkeypatch, [(feed, [_entry("a"), _entry("b")])])

    res = _accum.run(
        Path("ignored.toml"), cache_path=tmp_path / "c.json", seen_path=seen_path
    )
    assert res.skipped_duplicate == 1
    assert res.captured == 1
    assert [e["title"] for e in captured] == ["b"]


def test_accumulate_records_captured_entry_in_seen_store(monkeypatch, tmp_path):
    seen_path = tmp_path / "seen.json"
    feed = {"name": "f", "url": "https://e/f"}
    monkeypatch.setattr(_accum._capture, "capture_entry", _ok())
    _patch_feeds(monkeypatch, [(feed, [_entry("a")])])

    _accum.run(Path("ignored.toml"), cache_path=tmp_path / "c.json", seen_path=seen_path)

    store = _fetch.load_feed_cache(seen_path)
    assert _dedup.entry_key(_entry("a")) in store["https://e/f"]


def test_accumulate_failed_capture_not_recorded_in_seen(monkeypatch, tmp_path):
    """A capture that fails must not enter the seen-store, so it is retried."""
    seen_path = tmp_path / "seen.json"
    feed = {"name": "f", "url": "https://e/f"}
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: _capture.CaptureResult(status="no-cli"),
    )
    _patch_feeds(monkeypatch, [(feed, [_entry("a")])])

    _accum.run(Path("ignored.toml"), cache_path=tmp_path / "c.json", seen_path=seen_path)

    store = _fetch.load_feed_cache(seen_path)
    assert _dedup.entry_key(_entry("a")) not in store.get("https://e/f", [])


def test_accumulate_dry_run_does_not_persist_seen(monkeypatch, tmp_path):
    seen_path = tmp_path / "seen.json"
    feed = {"name": "f", "url": "https://e/f"}
    monkeypatch.setattr(_accum._capture, "capture_entry", _ok())
    _patch_feeds(monkeypatch, [(feed, [_entry("a")])])

    _accum.run(
        Path("ignored.toml"),
        cache_path=tmp_path / "c.json",
        seen_path=seen_path,
        dry_run=True,
    )
    assert not seen_path.exists()


def test_accumulate_trims_seen_store_to_cap(monkeypatch, tmp_path):
    seen_path = tmp_path / "seen.json"
    feed = {"name": "f", "url": "https://e/f"}
    existing = [f"old{i}" for i in range(_accum.MAX_SEEN_PER_FEED)]
    _fetch.save_feed_cache(seen_path, {"https://e/f": existing})
    monkeypatch.setattr(_accum._capture, "capture_entry", _ok())
    _patch_feeds(monkeypatch, [(feed, [_entry("brand-new")])])

    _accum.run(Path("ignored.toml"), cache_path=tmp_path / "c.json", seen_path=seen_path)

    kept = _fetch.load_feed_cache(seen_path)["https://e/f"]
    assert len(kept) == _accum.MAX_SEEN_PER_FEED
    assert _dedup.entry_key(_entry("brand-new")) in kept  # newest kept
    assert "old0" not in kept  # oldest evicted


def test_accumulate_dedup_is_per_feed_not_global(monkeypatch, tmp_path):
    """Same story URL across TWO feeds is captured by BOTH — per-feed scope
    deliberately preserves cross-source corroboration."""
    seen_path = tmp_path / "seen.json"
    f1 = {"name": "f1", "url": "https://e/f1"}
    f2 = {"name": "f2", "url": "https://e/f2"}
    shared = _entry("shared-story")
    monkeypatch.setattr(_accum._capture, "capture_entry", _ok())
    _patch_feeds(monkeypatch, [(f1, [dict(shared)]), (f2, [dict(shared)])])

    res = _accum.run(
        Path("ignored.toml"), cache_path=tmp_path / "c.json", seen_path=seen_path
    )
    assert res.captured == 2
    assert res.skipped_duplicate == 0


def test_accumulate_same_key_failure_not_recorded_in_seen(monkeypatch, tmp_path):
    """Two entries in one feed sharing an entry_key, one ok + one failed: the
    key must NOT be recorded (the failed one must stay retryable next run)."""
    seen_path = tmp_path / "seen.json"
    feed = {"name": "f", "url": "https://e/f"}
    e1 = {"title": "x", "link": "https://e/dup", "summary_excerpt": "a"}
    e2 = {"title": "y", "link": "https://e/dup", "summary_excerpt": "b"}  # same key
    statuses = iter(["ok", "no-cli"])
    monkeypatch.setattr(
        _accum._capture,
        "capture_entry",
        lambda entry, dry_run=False: _capture.CaptureResult(status=next(statuses)),
    )
    _patch_feeds(monkeypatch, [(feed, [e1, e2])])

    _accum.run(Path("ignored.toml"), cache_path=tmp_path / "c.json", seen_path=seen_path)

    store = _fetch.load_feed_cache(seen_path)
    assert _dedup.entry_key(e1) not in store.get("https://e/f", [])
