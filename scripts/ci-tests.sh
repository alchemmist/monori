#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$root/ci/docker-compose.integration.yml"
project="monori-ci-tests"
read -r -a compose_command <<<"${COMPOSE:-docker compose}"

cleanup() {
  "${compose_command[@]}" -f "$compose_file" -p "$project" down \
    --volumes --timeout 1 >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${compose_command[@]}" -f "$compose_file" -p "$project" up \
  --build --detach --wait fake-github

cd "$root"
GITHUB_ACTIONS_BOT_LOGIN='github-actions[bot]' \
  GITHUB_API_URL="http://127.0.0.1:${FAKE_GITHUB_HOST_PORT:-18080}" \
  GITHUB_EVENT_PATH="$root/ci/tests/integration/issue_comment_event.json" \
  GITHUB_REPOSITORY='alchemmist/monori' \
  GITHUB_TOKEN='fake-token' \
  uv run --locked --group test pytest -q ci/tests/integration "$@"
