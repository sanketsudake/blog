# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Hugo static site for `ssudake.com` — Sanket's personal blog (technical posts on Kubernetes, distributed systems, AI infra) and a talks index.
The Congo theme is consumed as a Hugo Module via `go.mod` (`github.com/jpanther/congo/v2`), so there is no `themes/` directory and Go is required to build.

Hugo is pinned in CI to `0.157.0` and Go to `1.26.1` (`.github/workflows/publish.yml`).
Match those locally if a build behaves oddly.

### Theme overrides to re-diff on Congo upgrade

Most of `layouts/` is upgrade-safe (custom talks layouts, shortcodes, robots.txt, llms.txt templates, and an `rss.xml` that overrides Hugo's *embedded* template, not a Congo one).
But three files copy a **Congo module partial/layout** and patch it — after any `hugo mod get -u`, re-diff each against the new module version (`~/Library/Caches/hugo_cache/modules/.../jpanther/congo/v2@<ver>/layouts/`) and re-apply the change:

- `layouts/_partials/schema.html` — adds `image`, `BlogPosting` type, `publisher`, and a URL-form `mainEntityOfPage` to the Article JSON-LD.
  Only the `.IsPage` block differs from upstream.
- `layouts/single.html` — identical to upstream except one added line in the footer: `{{ partial "related.html" . }}` (related posts, driven by the `[related]` config in `hugo.toml` and `layouts/_partials/related.html`).
- `layouts/_partials/recent-articles.html` — renders the homepage "Recent" list compact (title + meta only), dropping the summary and thumbnail blocks that upstream's `article-link.html` would emit.
  Exists because `list.showSummary = true` (in `params.toml`) is global: it should enrich the `/posts/` and taxonomy lists but *not* clutter the landing page.
  Re-diff against upstream `_partials/article-link.html`.

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

Use the semantic `classDef` palette and rules in the `author-mermaid-diagram` skill — color nodes by role (leader, lease, resource, …) so flow/sequence diagrams read at a glance.
Class every node once you class one.

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

Python tooling runs from the gitignored `.venv/`; secrets in a gitignored `.env` (template `.env.example`) — never commit it.

- **Social cards:** generate with the `generate-og-images` skill (`--brand ssudake.com --author "Sanket Sudake"`).
  Posts/talk-bundles ship a `feature.png`; flat talks set `images = ["og/talks/<slug>.png"]`; `static/og/default.png` is the site default.
  `content/posts/_index.md` sets `[cascade] feature = "no-onpage-feature"` so the card is social-only, not an on-page hero.
  Regenerate when a title or tags change.
- **LLM-friendliness:** `/llms.txt`, `/llms-full.txt`, and per-page markdown twins are generated via Hugo output formats — see the `add-llms-txt` skill.
  `robots.txt` allows the major AI crawlers.
  Don't hand-edit `public/`.
- **Audit & loop:** run the `audit-static-site` skill against `public/` (must report 0 errors); the on-demand `reachability-loop` skill ties audit + `report-site-analytics` into a measure→fix→log cycle (`docs/reachability/`).

## AGENTS.md

`AGENTS.md` at the repo root is a symlink to this file so other agentic tools (Codex, Cursor, Copilot) read the same guidance.
Edit `CLAUDE.md` only; do not duplicate content into `AGENTS.md`.
