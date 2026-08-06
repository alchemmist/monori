#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fe="$root/web/coverage/coverage-summary.json"
be="$root/server/coverage.json"
ci="$root/ci/coverage.json"

echo "collecting frontend coverage..." >&2
(cd "$root/web" && npx vitest run --coverage >/dev/null)

echo "collecting Python coverage..." >&2
(cd "$root" && uv run --locked --group test coverage erase)
(cd "$root" && uv run --locked --group test pytest -q server/tests \
  --cov=monori.server --cov=monori.common \
  --cov-report= --cov-append --cov-fail-under=0 >/dev/null)
(cd "$root" && COMPOSE="${COMPOSE:-docker compose}" bash scripts/ci-tests.sh \
  --cov=monori.ci --cov-report="json:$be" --cov-report= --cov-append >/dev/null)
(cd "$root" && uv run --locked --group test coverage report --include="ci/*" --fail-under=90)

cp "$be" "$ci"

jq -rn --slurpfile fe "$fe" --slurpfile be "$be" -f "$root/scripts/coverage-tree.jq"
