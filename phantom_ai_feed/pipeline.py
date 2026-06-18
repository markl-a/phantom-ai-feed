"""Run the full phantom-ai-feed pipeline by chaining existing stages.

This module does not reimplement stage logic. Daily mode runs
digest -> interview questions, registering SRS cards. Weekly mode adds
weekly -> newsletter after the daily chain. The pipeline stops on the first
stage error.

Note: digest always writes for the current calendar day because it uses
``date.today()`` internally, so ``--date`` should normally be today. The date
governs the interview, weekly, and newsletter window.
"""

import argparse
import datetime as _dt
import sys
from pathlib import Path

from . import digest as _digest
from . import interview_questions as _iq
from . import newsletter as _newsletter
from . import srs as _srs
from . import weekly as _weekly


DEFAULT_BASE = Path.home() / ".phantom-mesh" / "logs" / "phantom-ai-feed"


def _run_stage(name, fn):
    print(f"[pipeline] -> {name}", file=sys.stderr)
    try:
        return fn()
    except (SystemExit, Exception) as e:
        print(f"[pipeline] stage {name!r} aborted: {e}", file=sys.stderr)
        raise SystemExit(1)


def run(
    base_dir=DEFAULT_BASE,
    *,
    feeds_toml=None,
    end=None,
    weekly=False,
    use_stub=False,
    top_n=3,
    force=False,
    strict=False,
    srs_store=None,
) -> list[Path]:
    end = end or _dt.date.today()
    base_dir = Path(base_dir)
    srs_store = Path(srs_store) if srs_store else base_dir / "srs.jsonl"
    feeds_toml = Path(feeds_toml) if feeds_toml else _digest.DEFAULT_FEEDS

    artifacts: list[Path] = []
    artifacts.append(
        _run_stage(
            "digest",
            lambda: _digest.run(
                feeds_toml,
                base_dir,
                use_stub=use_stub,
                top_n=top_n,
                force=force,
                strict=strict,
            ),
        )
    )
    artifacts.append(
        _run_stage(
            "interview_questions",
            lambda: _iq.run(
                base_dir,
                end,
                use_stub=use_stub,
                srs_store=srs_store,
            ),
        )
    )
    artifacts.append(srs_store)
    review_out = srs_store.parent / f"srs-due-{end.isoformat()}.md"
    artifacts.append(
        _run_stage(
            "srs_review",
            lambda: _srs._write_review(review_out, end, _srs.due_cards(srs_store, end)),
        )
    )

    if weekly:
        artifacts.append(
            _run_stage(
                "weekly",
                lambda: _weekly.run(
                    feeds_toml,
                    base_dir,
                    use_stub=use_stub,
                    force=force,
                    strict=strict,
                ),
            )
        )
        artifacts.append(
            _run_stage(
                "newsletter",
                lambda: _newsletter.run(base_dir, end, force=force),
            )
        )

    return artifacts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="run phantom-ai-feed stages in a single chained pipeline"
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--daily", action="store_false", dest="weekly", default=False)
    mode.add_argument("--weekly", action="store_true", dest="weekly")
    ap.add_argument("--date", type=_dt.date.fromisoformat, default=_dt.date.today())
    ap.add_argument(
        "--base-dir",
        "--out",
        "--log-dir",
        dest="base_dir",
        type=Path,
        default=DEFAULT_BASE,
    )
    ap.add_argument("--feeds", type=Path, default=_digest.DEFAULT_FEEDS)
    ap.add_argument("--srs-store", type=Path, default=None)
    ap.add_argument("--use-stub", action="store_true")
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)

    run(
        args.base_dir,
        feeds_toml=args.feeds,
        end=args.date,
        weekly=args.weekly,
        use_stub=args.use_stub,
        top_n=args.top_n,
        force=args.force,
        strict=args.strict,
        srs_store=args.srs_store,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
