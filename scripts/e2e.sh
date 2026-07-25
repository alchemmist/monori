#!/usr/bin/env bash
# e2e runner behind `make t-slow`: brings up the isolated full stack
# (deploy/docker-compose.test.yml — real API + production web build + throwaway
# database), waits until it answers, runs the Playwright suite against it and
# always tears the stack down, even on failure. Local and CI run this same
# script — CI only adds toolchain caching around it.
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE=${COMPOSE:-"docker compose"}
# exported so the compose file's "${E2E_PORT:-8078}:8000" publishes the same
# port the probe and Playwright talk to
export E2E_PORT=${E2E_PORT:-8078}
BASE_URL=${E2E_BASE_URL:-"http://localhost:${E2E_PORT}"}

stack() {
  # shellcheck disable=SC2086 # COMPOSE is intentionally two words ("docker compose")
  $COMPOSE -f deploy/docker-compose.test.yml -p monori-e2e "$@"
}

cleanup() {
  stack down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

stack up --build --detach

echo "waiting for the e2e stack on ${BASE_URL} ..."
ready=""
for _ in $(seq 1 120); do
  if curl -fsS --connect-timeout 1 --max-time 2 "${BASE_URL}/openapi.json" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [ -z "$ready" ]; then
  echo "e2e stack did not become healthy" >&2
  stack logs
  exit 1
fi

# subshell: the cleanup trap resolves the compose file relative to the repo
# root, so the script's own cwd must not move
(cd web && E2E_BASE_URL="$BASE_URL" npx playwright test "$@")
