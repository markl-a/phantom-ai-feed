# Source Registry Policy

`sources/feeds.toml` is the canonical public source registry for
`phantom-ai-feed`. It is intentionally simple: a flat list of public RSS or Atom
feeds that can be fetched without private credentials.

## Registry Rules

Each `[[feed]]` entry must include:

- `name`: stable, unique identifier used in output and tests.
- `url`: public `http://` or `https://` RSS/Atom endpoint.
- `category`: coarse grouping such as `research`, `blog`, `community`, `zh`,
  `youtube`, `podcast`, or `ptt`.

Optional breadth sources must also include:

- `optional = true`

## Core Versus Optional Sources

The strict core is the set of feeds without `optional = true`. A strict run:

```powershell
$env:PHANTOM_AI_FEED_OFFLINE = "1"
python -m phantom_ai_feed.digest --use-stub --strict --force --out <temp>
```

must keep the core feeds and skip optional feeds. This keeps CI, demos, and
first-run checks stable even when broader live sources drift or rate-limit.

Optional feeds are still first-class inputs for normal runs. They provide source
breadth across blogs, newsletters, YouTube channel feeds, podcasts, PTT boards,
and Chinese-language technology media, but they must not be required for the
package to look healthy.

## Test And Demo Policy

- Tests must stay hermetic. They should use fixtures, monkeypatching, or
  `PHANTOM_AI_FEED_OFFLINE=1`; they must not require network availability.
- Live reachability checks are allowed only as explicit manual verification or
  separately gated jobs.
- Public examples must use synthetic data or intentionally public feed content.
- No private credentials, cookies, reading logs, annotations, or local recall
  databases may be committed.

## Closed Or Fragile Platforms

Closed platforms that need login, cookies, scraping, or private APIs are out of
the strict core. If they are ever supported, they must be implemented as
optional adapters with explicit opt-in configuration and no committed secrets.

## Source Changes

When adding or removing feeds:

1. Prefer public RSS/Atom endpoints that do not require an API key.
2. Mark broad, experimental, rate-limited, or fragile feeds as `optional = true`.
3. Preserve unique feed names.
4. Update tests or documentation when registry semantics change.
