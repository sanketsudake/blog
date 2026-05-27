# Reachability cycle log

Each `<date>-cycle.md` here records one pass of the on-demand improvement loop (`.claude/skills/reachability-loop/`): the signals observed, the changes made, the hypotheses behind them, and what to re-measure next time.

The loop reads the most recent file here first, so it can report deltas instead of starting cold.
Keep these committed — they are the project's reach history and contain no traffic data (the raw GA4/GSC snapshots under `docs/analytics/` are gitignored).

## Per-cycle template

```markdown
# Reachability cycle — <YYYY-MM-DD>

## Signals
- Audit: <top structural findings>
- Search (GSC): <key queries — impressions/CTR/position>
- Behaviour (GA4): <top pages, channels, notable shifts>

## Deltas since last cycle
- <what improved / regressed vs the previous cycle>

## Changes made
- <file>: <what> — <why>

## Hypotheses / re-measure next time
- <change> should move <metric> for <page/query>; check next cycle.
```
