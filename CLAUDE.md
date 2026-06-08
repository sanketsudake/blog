# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Hugo static site for `ssudake.com` — Sanket's personal blog (technical posts on Kubernetes, distributed systems, AI infra) and a talks index.
The Congo theme is consumed as a Hugo Module via `go.mod` (`github.com/jpanther/congo/v2`), so there is no `themes/` directory and Go is required to build.

Hugo is pinned in CI to `0.157.0` and Go to `1.26.1` (`.github/workflows/publish.yml`).
Match those locally if a build behaves oddly.

### Theme overrides to re-diff on Congo upgrade

Most of `layouts/` is upgrade-safe (custom talks layouts, shortcodes, robots.txt, llms.txt templates, and an `rss.xml` that overrides Hugo's *embedded* template, not a Congo one).
But two files copy a **Congo module partial/layout** and patch it — after any `hugo mod get -u`, re-diff each against the new module version (`~/Library/Caches/hugo_cache/modules/.../jpanther/congo/v2@<ver>/layouts/`) and re-apply the change:

- `layouts/_partials/schema.html` — adds `image`, `BlogPosting` type, `publisher`, and a URL-form `mainEntityOfPage` to the Article JSON-LD. Only the `.IsPage` block differs from upstream.
- `layouts/single.html` — identical to upstream except one added line in the footer: `{{ partial "related.html" . }}` (related posts, driven by the `[related]` config in `hugo.toml` and `layouts/_partials/related.html`).

## Build, serve, deploy

```bash
hugo server -D            # local preview at http://localhost:1313 (drafts on)
hugo                       # production build into public/
hugo mod get -u            # refresh the Congo theme module
hugo mod tidy
```

Deploy is automatic: pushing to `master` triggers `.github/workflows/publish.yml`, which builds with Hugo `0.157.0` and pushes the rendered site to `sanketsudake/sanketsudake.github.io@master` (CNAME `ssudake.com`) using `SYNC_BUILD_TOKEN`.
There are no tests and no linter — `hugo` itself is the only check that needs to pass before merge.

## Content layout — the conventions that matter

**Posts live as page bundles** under `content/posts/<slug>/index.md`, with images committed next to `index.md` and referenced by relative path.
Don't put post assets under `static/` or `assets/images/` — those are reserved for site-wide assets (favicons, the author photo, event images used outside posts).

Posts use **TOML frontmatter** (`+++ ... +++`); talks use **YAML frontmatter** (`--- ... ---`).
This split is intentional, not a mistake — preserve it when editing.

Required post frontmatter fields, in this order:

```toml
+++
title = "…"
date = 2026-04-25T10:00:00+05:30
tags = ["kubernetes", "…"]
categories = []
summary = "…"
canonicalURL = "https://www.infracloud.io/blogs/<slug>/"   # only if cross-posted
showTableOfContents = true
+++
```

`showTableOfContents = true` is set on every post — keep it.
`categories` is intentionally empty across the site; tags do the categorisation work.

If a post is cross-posted (most older ones are), include `canonicalURL` **and** open the body with the attribution blockquote used elsewhere:

```markdown
> *This post was originally published on [InfraCloud's blog](<canonical URL>).*
```

Posts originally published here (e.g. the leader-election post) omit both `canonicalURL` and the attribution blockquote.

## Talks section

Talks live under `content/talks/` either as a single `<slug>.md` (slideshare-only) or a page bundle `content/talks/<slug>/index.md` with event photos alongside.
Required talk frontmatter: `title`, `date`, `slug`, `event`, `summary`; optional `gallery` is a list of image filenames in the same directory.

Talks have **custom layouts** (not Congo's defaults):

- `layouts/talks/list.html` — groups talks by year, shows event icon + summary, renders a thumbnail when `gallery[0]` resolves.
- `layouts/talks/single.html` — renders the body, then a `gallery` grid with a click-to-zoom lightbox.

If you change talk frontmatter shape, update both files.
Gallery filenames must match exactly; missing matches silently render no thumbnail.

The slideshare embed uses the custom shortcode `{{< slideshare key="…" >}}` defined in `layouts/shortcodes/slideshare.html`.
The `key` is the trailing path segment of the SlideShare embed URL.

`presentations/` holds the source `.pptx` decks for talks but is **not** part of the rendered site — don't link to it from content.

## Diagrams and code in posts

Mermaid renders natively under Congo via the `{{< mermaid >}}` shortcode — see `content/posts/leader-election-strategies-for-kubernetes-operators/index.md` for examples.
Prefer Mermaid over committed image assets when a diagram is structural (flow, sequence, ER) so it stays editable in source.

### Mermaid theme — color nodes by semantic role

Congo's default Mermaid theme renders every node in the same primary color, which is fine for a one-node decision tree but hides meaning in flow / sequence diagrams.
We apply a small **semantic palette** via Mermaid's `classDef` so that role (leader, standby, lease, etc.) reads at a glance, in both light and dark mode.

Pick from this palette — Tailwind 400/500-level mid-tones with white text, chosen for contrast on either background:

| Class      | Use for                                            | Fill      | Stroke    |
|------------|----------------------------------------------------|-----------|-----------|
| `leader`   | Active / primary actor (the one doing the work)    | `#10b981` | `#047857` |
| `standby`  | Passive / waiting (failover candidate, hot spare)  | `#94a3b8` | `#475569` |
| `lease`    | Coordination primitive (Lease, bucket, lock)       | `#f59e0b` | `#b45309` |
| `resource` | Resource being acted on (CR, DB row, target state) | `#fb7185` | `#be123c` |
| `external` | External system (API, gateway, third-party)        | `#64748b` | `#334155` |
| `process`  | Logic / decision step / generic action             | `#38bdf8` | `#0369a1` |
| `pod`      | Workload pod *when in conflict / uncoordinated*    | `#fb7185` | `#be123c` |

All classes use `color:#fff` for the label.
Only declare and apply the classes a given diagram needs — don't paste the whole palette into every block.
Once you class one node in a diagram, class **every** node — mixing classed nodes (white text) and unclassed nodes (Congo's neutral text) looks broken.

Append the `classDef` lines and the `class` lines at the bottom of the diagram body, before the closing shortcode:

```text
{{< mermaid >}}
flowchart TD
    A[Pod starts] --> B[Compete for Lease]
    B -->|won| C[Leader]
    B -->|lost| D[Standby]
    classDef process fill:#38bdf8,stroke:#0369a1,color:#fff
    classDef lease fill:#f59e0b,stroke:#b45309,color:#fff
    classDef leader fill:#10b981,stroke:#047857,color:#fff
    classDef standby fill:#94a3b8,stroke:#475569,color:#fff
    class A process
    class B lease
    class C leader
    class D standby
{{< /mermaid >}}
```

Inside a `subgraph`, place the `classDef` / `class` lines **after** the matching `end`, not inside the subgraph body.

Keep code snippets in posts minimal — the existing pattern is "one canonical snippet to anchor the idea, then link to the repo for the full implementation."
Don't paste large Go files inline.

## Markdown style

The user enforces **one sentence per line** in all markdown (rendered HTML is unchanged because CommonMark collapses single newlines into spaces, but `git diff` becomes per-sentence).
Run `python3 scripts/md-one-sentence-per-line.py <file>` after substantial prose edits — it preserves frontmatter, fenced code, Hugo shortcodes, tables, blockquotes, and HTML comments.
Use `--check` in scripts and `--diff` to preview.

When drafting, the user writes inline review notes as `<!-- REVIEW: … -->` HTML comments — the formatter preserves them, and they are stripped by Hugo at render time.
Don't remove them unless the user has resolved them.

## Writing voice (for new post drafts)

These are derived from existing posts; mirror them when ghost-drafting.

- Open with a concrete scenario or incident, not an abstract definition (`coredns-kubernetes` opens with a 5xx incident; the leader-election post opens with `kubectl scale --replicas=3` going wrong).
- Second person, conversational ("you", "we"), but technically dense — no filler.
- Section headings are full sentences or claims, not single nouns ("Why one operator replica isn't enough", not "Background").
- Italic blockquote callouts for the one or two non-obvious insights per post.
- Standard sign-off at the bottom: `We'd love to hear your thoughts on this post — start a conversation on [LinkedIn](https://www.linkedin.com/in/sanketsudake/).`
- Length target for comprehensive guides: ~2500–3000 words, comparable to the NVIDIA GPU Operator post.

## Planning before drafting

The user uses `superpowers:brainstorming` and `superpowers:writing-plans` before any non-trivial post.
Drafts are spec'd in `docs/superpowers/specs/<YYYY-MM-DD>-<slug>-design.md` first — see `docs/superpowers/specs/2026-04-25-leader-election-blog-post-design.md` for the format (goal, decisions table, section-by-section outline, length target, out-of-scope list).
For a new post, create the spec in that directory before touching `content/posts/`.

## Config gotchas

- Site config is split across `config/_default/{hugo.toml,languages.en.toml,menus.en.toml,module.toml,params.toml}` — there is **no** root `config.toml` (the `config.toml.bkp` at the repo root is a stale backup, not loaded).
- `params.toml` configures the homepage as Congo's `profile` layout pointing to `assets/images/sanket_sudake.jpg`.
  The headline/bio there is the actual home page copy.
- Menu order is controlled by `weight` in `menus.en.toml` (Blog 10, Talks 20, About 30).
- Custom CSS lives in `assets/css/custom.css` (Tailwind-friendly classes referenced from the talks layouts).

## Social images & reachability tooling

Python tooling lives in `scripts/` and runs from the gitignored `.venv/` (`python3 -m venv .venv && .venv/bin/pip install Pillow google-genai google-analytics-data google-api-python-client google-auth`).
Secrets go in a gitignored `.env` (template: `.env.example`) — never commit it.

**Social-share images.**
Hugo's embedded `opengraph`/`twitter_cards` templates resolve `og:image` from frontmatter `images`, then a bundle resource matching `*feature*`, then site-level `params.images`; the Twitter card auto-upgrades to `summary_large_image` once any image exists.
So every page gets a card: posts/talk-bundles ship a `feature.png`, flat talks set `images = ["og/talks/<slug>.png"]` (file under `static/og/talks/`), and `static/og/default.png` (set in `params.images`) covers everything else.
Generate them with `scripts/gen-og-image.py` — a branded 1200×630 card with the title/tags/brand overlaid by Pillow over a Nano Banana (`GEMINI_API_KEY`, paid tier), `--bg`, or gradient-fallback background.

When adding a post or talk, regenerate its card: `.venv/bin/python scripts/gen-og-image.py <path-to-index.md-or-flat.md>` (or `--all-content` for everything; `--default` for the site card).
Manual background workflow (no API billing): `--print-prompts` emits a per-item prompt to paste into the Gemini app, then drop the downloaded PNGs named `<slug>.png` into a folder and run `--bg-dir <folder>`.
The `feature.png` is a social card only — `content/posts/_index.md` has a `[cascade] feature = "no-onpage-feature"` so Congo does **not** render it as an on-page hero (it would just repeat the title); `og:image` is unaffected.
If you change a post/talk **title or tags**, regenerate its card so the text matches.

**LLM-friendliness.**
`robots.txt` (`layouts/robots.txt`) explicitly allows the major AI crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, …).
`/llms.txt` and `/llms-full.txt` are **generated** from content via the `llms`/`llmsfull` output formats (`config/_default/hugo.toml`) and the `layouts/index.llms*.txt` templates — they stay in sync as content is added, so don't hand-edit `public/`.
`llms.txt` is a link index (posts + talks, with canonical URLs for syndicated posts); `llms-full.txt` inlines full post bodies (posts only).

**Audit & the improvement loop.**
`scripts/site-audit.py` crawls the built `public/` and flags SEO/UX issues (`docs/audit/<date>.md`; `--check` exits non-zero on errors) — run it after `hugo`, it should report 0 errors.
`scripts/analytics-report.py` pulls GA4 + Search Console (setup in `docs/analytics/SETUP.md`; reports are gitignored).
The on-demand `reachability-loop` skill (`.claude/skills/reachability-loop/`) ties these into a measure → prioritize → fix → log cycle; cycle logs live in `docs/reachability/`.

## AGENTS.md

`AGENTS.md` at the repo root is a symlink to this file so other agentic tools (Codex, Cursor, Copilot) read the same guidance.
Edit `CLAUDE.md` only; do not duplicate content into `AGENTS.md`.
