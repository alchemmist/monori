#!/usr/bin/env bash
set -euo pipefail
npm run build --prefix web
uv run --locked python -m monori.ci.quality_graph.checks.bundle_measurement measure --dist web/dist --output "$RUNNER_TEMP/current-bundle.json"
git worktree add --detach "$RUNNER_TEMP/base-repo" "$BASE"
npm ci --no-audit --no-fund --prefix "$RUNNER_TEMP/base-repo/web"
npm run build --prefix "$RUNNER_TEMP/base-repo/web"
uv run --locked python -m monori.ci.quality_graph.checks.bundle_measurement measure --dist "$RUNNER_TEMP/base-repo/web/dist" --output "$RUNNER_TEMP/base-bundle.json"
mkdir -p "$RUNNER_TEMP/bundle-size"
uv run --locked python -m monori.ci.quality_graph.checks.bundle_measurement compare --base "$RUNNER_TEMP/base-bundle.json" --current "$RUNNER_TEMP/current-bundle.json" --output "$RUNNER_TEMP/bundle-size/report.json" --pr-number "$PR_NUMBER" --head-sha "$HEAD_SHA"
