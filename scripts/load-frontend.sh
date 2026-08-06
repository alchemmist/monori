#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE=${COMPOSE:-"docker compose"}
LOAD_OUTPUT_DIR=${LOAD_OUTPUT_DIR:-"$PWD/reports/perf"}
E2E_PORT=${E2E_PORT:-8078}
export E2E_PORT
export CONTAINER_PLATFORM=${CONTAINER_PLATFORM:-"linux/$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"}
base_url="http://localhost:$E2E_PORT"
harness="$PWD/tools/frontend-perf"
project="monori-load-frontend-$$"
token_file="$LOAD_OUTPUT_DIR/frontend-token.json"
lighthouse_dir="$LOAD_OUTPUT_DIR/lighthouse"

case "$LOAD_OUTPUT_DIR" in
"" | "/" | "$PWD")
  echo "frontend load: refusing unsafe LOAD_OUTPUT_DIR '$LOAD_OUTPUT_DIR'" >&2
  exit 2
  ;;
esac

stack() {
  read -r -a command <<<"$COMPOSE"
  "${command[@]}" -f deploy/docker-compose.test.yml -p "$project" "$@"
}

trap 'rm -f "$token_file"; rm -rf "$harness/.lighthouseci"; stack down --volumes --remove-orphans >/dev/null 2>&1 || true' EXIT

mkdir -p "$LOAD_OUTPUT_DIR"
rm -rf "$lighthouse_dir" "$harness/.lighthouseci"
stack up --build --detach

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
  exit 1
fi

lhci="$harness/node_modules/.bin/lhci"
if [ ! -x "$lhci" ]; then
  echo "Lighthouse CI is missing; run make install" >&2
  exit 2
fi
chrome_path=$(cd "$harness" && node -e 'const { chromium } = require("playwright"); process.stdout.write(chromium.executablePath())')
if [ ! -x "$chrome_path" ]; then
  echo "Playwright Chromium is missing; run cd tools/frontend-perf && npx playwright install chromium" >&2
  exit 2
fi

(cd "$harness" && PERF_BASE_URL="$base_url" node prepare.mjs "$token_file")
(
  cd "$harness"
  PERF_BASE_URL="$base_url" PERF_TOKEN_FILE="$token_file" PERF_CHROME_PATH="$chrome_path" "$lhci" collect --config=lighthouserc.cjs
  PERF_BASE_URL="$base_url" node navigation.mjs "$token_file" "$LOAD_OUTPUT_DIR/navigation.json"
)
mkdir -p "$lighthouse_dir"
cp "$harness"/.lighthouseci/*.json "$lighthouse_dir/"
(cd "$harness" && node baseline.mjs "$lighthouse_dir" "$LOAD_OUTPUT_DIR/navigation.json" "$LOAD_OUTPUT_DIR")
