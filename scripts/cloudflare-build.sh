#!/usr/bin/env bash
# Cloudflare Workers Builds entrypoint for the Hugo site.
#
# Wired up in: Workers project -> Settings -> Build -> Build command:
#   bash scripts/cloudflare-build.sh
#
# Production (master) builds use the baseURL from config/_default/hugo.toml
# (https://ssudake.com/) and run with `-e production`, which layers in
# config/production/hugo.toml — the only place the Google Analytics ID
# is configured. Preview builds on every other branch run with `-e
# preview`, which has no overlay directory, so GA is never injected
# into preview HTML and analytics stays clean of *.workers.dev traffic.
#
# Previews also override baseURL with the per-branch *.workers.dev URL
# so asset references and Hugo's SRI integrity hashes resolve
# same-origin — otherwise the preview HTML points at ssudake.com for
# its CSS/JS, fails SRI's CORS check, and renders unstyled.
#
# Workers Builds doesn't inject a deployment-URL env var (Pages exposed
# CF_PAGES_URL; Workers Builds only gives us WORKERS_CI_BRANCH and
# WORKERS_CI_COMMIT_SHA), so we construct the URL from the branch name.
# The slug transform (lowercase + non-alphanumeric -> '-') matches
# Cloudflare's own subdomain sanitization, so 'feature/auth' becomes
# 'feature-auth' and lines up with the actual preview hostname.

set -euo pipefail

PRODUCTION_BRANCH="master"
WORKER_NAME="ssudake-blog"
ACCOUNT_SUBDOMAIN="sanketsudake"

if [ "${WORKERS_CI_BRANCH:-}" = "$PRODUCTION_BRANCH" ]; then
    hugo --gc --minify -e production
else
    slug=$(printf '%s' "${WORKERS_CI_BRANCH:-local}" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-')
    preview_url="https://${slug}-${WORKER_NAME}.${ACCOUNT_SUBDOMAIN}.workers.dev/"
    echo "Preview build for branch '${WORKERS_CI_BRANCH:-local}' -> baseURL ${preview_url}"
    hugo --gc --minify -e preview --baseURL "$preview_url"
fi
