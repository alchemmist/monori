#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fe="$root/web/coverage/coverage-summary.json"
be="$root/server/coverage.json"

echo "collecting frontend coverage..." >&2
(cd "$root/web" && npx vitest run --coverage >/dev/null 2>&1)

echo "collecting backend coverage..." >&2
(cd "$root/server" && uv run pytest -q --cov --cov-report="json:$be" --cov-report= >/dev/null 2>&1)

jq -rn --slurpfile fe "$fe" --slurpfile be "$be" -f "$root/scripts/coverage-tree.jq"
