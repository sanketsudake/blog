---
name: reachability-loop
description: Use on demand to review and improve the blog's reach (SEO, social previews, on-site UX). Runs the site audit + GA4/Search Console report, synthesizes a prioritized opportunity list, implements approved fixes per the repo's conventions, and logs each cycle so the next run can measure deltas. Trigger when the user asks to "improve the blog", "do a reachability/SEO pass", "what should I fix on the site", or run the improvement loop.
---

# Reachability improvement loop

A repeatable, on-demand cycle: **measure → synthesize → propose → implement → log**.
Run it roughly monthly (Search Console lags ~3 days and trends need weeks).

All commands run from the repo root.
Use the tooling venv: `.venv/bin/python`.

## 1. Measure

```bash
hugo --logLevel error                          # rebuild public/
.venv/bin/python scripts/site-audit.py         # -> docs/audit/<date>.md  (structural)
.venv/bin/python scripts/analytics-report.py   # -> docs/analytics/<date>.{md,json}  (behaviour + search)
```

- The **audit** is always available (pure structure).
  Read the new `docs/audit/<date>.md`.
- The **analytics** report needs one-time setup (`docs/analytics/SETUP.md`).
  If it reports "not available" / a scope or property error, surface the relevant SETUP step and continue with audit-only signals — do **not** block the cycle on it.

## 2. Diff against the last cycle

- Read the most recent prior `docs/reachability/<date>-cycle.md` and the previous `docs/analytics/*.json` (gitignored, local).
- Note what changed since: did a flagged issue get fixed? did a low-CTR query improve? did a fixed page gain clicks/position?
  State the deltas — this is the point of the loop.

## 3. Synthesize a prioritized opportunity list

Combine signals into concrete, ranked actions.
Mapping rules:

| Signal (source) | Action |
|---|---|
| High impressions + low CTR (GSC) | Rewrite the post `title`/`summary` to match intent; regenerate its OG image. |
| Position 5–20 "near-miss" query (GSC) | Strengthen that section's content; add internal links from related posts; tighten headings. |
| High-traffic page (GA4) | Add a clear next-step / internal links to related posts to spread authority and dwell. |
| Over-long / over-short title or description (audit) | Trim to the SERP-friendly range while keeping the hook. |
| Image missing alt text (audit) | Add descriptive alt (accessibility + image search). |
| Orphan / no inbound links (audit) | Link the page from a relevant post or list. |
| Thin post (audit) | Expand or merge; or de-prioritize from indexing. |
| Duplicate title/description (audit) | Differentiate them. |

Prioritize by **impact × ease**: search opportunities on already-indexed pages usually beat net-new content.
Present the ranked list to the user and get approval before editing.

## 4. Implement approved fixes — per repo conventions (`CLAUDE.md`)

- Posts use **TOML** frontmatter, talks use **YAML** — preserve the split.
- Keep `showTableOfContents = true`; `categories = []`.
- Cross-posted posts keep `canonicalURL` **and** the attribution blockquote; original posts omit both.
- After prose edits run `.venv/bin/python scripts/md-one-sentence-per-line.py <file>` (or `python3`).
- If you change a post/talk **title or tags**, regenerate its social image: `.venv/bin/python scripts/gen-og-image.py <path-to-index.md-or-file>` (the embedded Hugo templates pick up `feature.png` / `static/og/...` automatically — see the OG-image notes in the plan).
- Mermaid diagrams use the semantic palette in `CLAUDE.md`.
- Re-run `scripts/site-audit.py --check` after edits; it must report **0 errors**.

## 5. Log the cycle

Write `docs/reachability/<date>-cycle.md` capturing:

- **Signals** this cycle (top audit findings + key GSC/GA4 numbers).
- **Changes made** (files, what and why).
- **Hypotheses** (what each change should improve) and **what to re-measure next time** (specific query/page/metric).

This file is the loop's memory; the next run reads it first (step 2).
See `docs/reachability/README.md`.

## Out of scope

Off-site link building, paid promotion, and background scheduling — this loop is on-demand.
Don't commit or push unless the user asks.
