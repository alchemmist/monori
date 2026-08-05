#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fe="$root/web/coverage/coverage-summary.json"
be="$root/server/coverage.json"
ci="$root/ci/coverage.json"

echo "collecting frontend coverage..." >&2
(cd "$root/web" && npx vitest run --coverage >/dev/null)

echo "collecting Python coverage..." >&2
(cd "$root" && uv run --locked --group test pytest -q server/tests ci/tests \
  -m "not integration" \
  --cov=monori \
  --cov-report="json:$be" --cov-report= >/dev/null)

cp "$be" "$ci"

jq -rn --slurpfile fe "$fe" --slurpfile be "$be" -f "$root/scripts/coverage-tree.jq"
