#!/usr/bin/env bash
# Compare two production full stacks with the same deterministic account data.
set -euo pipefail

cd "$(dirname "$0")/.."

BASE=${BASE:-origin/main}
COMPOSE=${COMPOSE:-"docker compose"}
PERF_OUTPUT_DIR=${PERF_OUTPUT_DIR:-"$PWD/reports/frontend-perf"}
PR_NUMBER=${PR_NUMBER:-0}
HEAD_SHA=${HEAD_SHA:-$(git rev-parse HEAD)}
HARNESS="$PWD/tools/frontend-perf"
CONFIG="$HARNESS/config.json"
LHCI_BIN="$HARNESS/node_modules/.bin/lhci"
PYTHON=${PYTHON:-python3}

case "$PERF_OUTPUT_DIR" in
  "" | "/" | "$PWD")
    echo "frontend performance: refusing unsafe PERF_OUTPUT_DIR '$PERF_OUTPUT_DIR'" >&2
    exit 2
    ;;
esac

rm -rf "$PERF_OUTPUT_DIR/base" "$PERF_OUTPUT_DIR/pr"
rm -f \
  "$PERF_OUTPUT_DIR/report.json" \
  "$PERF_OUTPUT_DIR/summary.md" \
  "$PERF_OUTPUT_DIR/comment.md"

base_parent=$(mktemp -d)
base_worktree="$base_parent/base"
worktree_added=""
active_compose=""
active_project=""

stack() {
  # shellcheck disable=SC2086 # COMPOSE intentionally contains the executable and subcommand
  $COMPOSE -f "$active_compose" -p "$active_project" "$@"
}

cleanup_stack() {
  if [ -n "$active_compose" ]; then
    stack down --volumes --remove-orphans >/dev/null 2>&1 || true
    active_compose=""
    active_project=""
  fi
}

# shellcheck disable=SC2329 # called by the EXIT-trapped finish function
cleanup() {
  cleanup_stack
  rm -f "$PERF_OUTPUT_DIR/base/token.json" "$PERF_OUTPUT_DIR/pr/token.json"
  rm -rf "$HARNESS/.lighthouseci"
  if [ -n "$worktree_added" ]; then
    git worktree remove --force "$base_worktree" >/dev/null 2>&1 || true
  else
    rmdir "$base_worktree" >/dev/null 2>&1 || true
  fi
  rmdir "$base_parent" >/dev/null 2>&1 || true
}

# shellcheck disable=SC2329 # invoked through the EXIT trap below
finish() {
  code=$?
  cleanup
  if [ "$code" -ne 0 ] && [ ! -f "$PERF_OUTPUT_DIR/report.json" ]; then
    "$PYTHON" scripts/frontend_perf.py error \
      --output "$PERF_OUTPUT_DIR" \
      --message "The collector exited with status $code. See the workflow log for the failing step." \
      --pr-number "$PR_NUMBER" \
      --head-sha "$HEAD_SHA" || true
  fi
  exit "$code"
}
trap finish EXIT

wait_for_stack() {
  base_url=$1
  echo "waiting for the performance stack on $base_url ..."
  ready=""
  for _ in $(seq 1 180); do
    if curl -fsS --connect-timeout 1 --max-time 2 "$base_url/openapi.json" >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done
  if [ -z "$ready" ]; then
    stack logs
    echo "performance stack did not become healthy" >&2
    return 1
  fi
}

collect_revision() {
  label=$1
  source_root=$2
  port=$3
  output="$PERF_OUTPUT_DIR/$label"
  token_file="$output/token.json"
  base_url="http://localhost:$port"

  mkdir -p "$output/lighthouse"
  active_compose="$source_root/deploy/docker-compose.test.yml"
  active_project="monori-perf-$label-$$"

  echo "── building $label production stack ──"
  E2E_PORT="$port" stack up --build --detach
  wait_for_stack "$base_url"

  echo "── seeding $label through the real API and UI ──"
  (cd "$HARNESS" && PERF_BASE_URL="$base_url" node prepare.mjs "$token_file")

  rm -rf "$HARNESS/.lighthouseci"
  echo "── Lighthouse $label: three runs per route ──"
  (
    cd "$HARNESS"
    PERF_BASE_URL="$base_url" \
      PERF_TOKEN_FILE="$token_file" \
      PERF_CHROME_PATH="$chrome_path" \
      "$LHCI_BIN" collect --config=lighthouserc.cjs
  )
  cp "$HARNESS"/.lighthouseci/*.json "$output/lighthouse/"
  rm -rf "$HARNESS/.lighthouseci"

  echo "── SPA navigation $label: three runs per scenario ──"
  (
    cd "$HARNESS"
    PERF_BASE_URL="$base_url" node navigation.mjs "$token_file" "$output/navigation.json"
  )
  rm -f "$token_file"
  cleanup_stack
}

git rev-parse --verify --quiet "$BASE" >/dev/null || {
  echo "frontend performance: BASE='$BASE' is not a valid revision" >&2
  exit 2
}

if [ ! -x "$LHCI_BIN" ]; then
  echo "Lighthouse CI is missing; run: cd tools/frontend-perf && npm install" >&2
  exit 2
fi

chrome_path=$(
  cd "$HARNESS"
  node -e 'const { chromium } = require("playwright"); process.stdout.write(chromium.executablePath())'
)
if [ ! -x "$chrome_path" ]; then
  echo "Playwright Chromium is missing; run: cd tools/frontend-perf && npx playwright install chromium" >&2
  exit 2
fi

merge_base=$(git merge-base "$BASE" HEAD)
mkdir -p "$PERF_OUTPUT_DIR"
git worktree add --detach "$base_worktree" "$merge_base" >/dev/null
worktree_added=1

collect_revision base "$base_worktree" 8178
collect_revision pr "$PWD" 8178

set +e
GITHUB_RUN_URL=${GITHUB_RUN_URL:-} "$PYTHON" scripts/frontend_perf.py compare \
  --base-dir "$PERF_OUTPUT_DIR/base" \
  --pr-dir "$PERF_OUTPUT_DIR/pr" \
  --config "$CONFIG" \
  --output "$PERF_OUTPUT_DIR" \
  --pr-number "$PR_NUMBER" \
  --head-sha "$HEAD_SHA"
gate=$?
set -e

if [ -f "$PERF_OUTPUT_DIR/summary.md" ]; then
  sed -n '1,240p' "$PERF_OUTPUT_DIR/summary.md"
fi
exit "$gate"
