#!/usr/bin/env bash
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fe="$root/web/coverage/coverage-summary.json"
be="$root/server/coverage.json"

# Collect both sides even if one gate fails: the tree and the other side's
# numbers are the whole point of running this, so a threshold miss must not
# swallow the report. Statuses are re-raised at the end.
echo "collecting frontend coverage..." >&2
(cd "$root/web" && npx vitest run --coverage >/dev/null)
fe_status=$?

echo "collecting backend coverage..." >&2
(cd "$root/server" && uv run pytest -q --cov --cov-report="json:$be" --cov-report= >/dev/null)
be_status=$?

if [[ -f "$fe" && -f "$be" ]]; then
    jq -rn --slurpfile fe "$fe" --slurpfile be "$be" -f "$root/scripts/coverage-tree.jq"
else
    echo "coverage tree skipped: coverage json missing (frontend or backend)" >&2
fi

if [[ $fe_status -ne 0 || $be_status -ne 0 ]]; then
    echo "coverage gate failed (frontend=$fe_status backend=$be_status)" >&2
    exit 1
fi
