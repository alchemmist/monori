#!/usr/bin/env bash
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fe="$root/web/coverage/coverage-summary.json"
be="$root/server/coverage.json"
be_xml="$root/server/coverage.xml"
ci="$root/ci/coverage.json"
status=0

echo "collecting frontend coverage..." >&2
(cd "$root/web" && npx vitest run --coverage >/dev/null) || status=$?

echo "collecting Python coverage..." >&2
(cd "$root" && uv run --locked --group test coverage erase) || status=$?
(cd "$root" && env -u GITHUB_STEP_SUMMARY -u MUTATION_SUMMARY_PATH uv run --locked --group test pytest -q server/tests \
  --cov=server/app --cov=common \
  --cov-report="json:$be" --cov-report="xml:$be_xml" --cov-report= \
  --cov-fail-under=0 >/dev/null) || status=$?
(cd "$root" && uv run --locked --group test coverage erase) || status=$?
(cd "$root" && env -u GITHUB_STEP_SUMMARY -u MUTATION_SUMMARY_PATH uv run --locked --group test pytest -q ci/tests \
  --cov=ci --cov-report="json:$ci" --cov-report= --cov-fail-under=0 >/dev/null) || status=$?
(cd "$root" && uv run --locked --group test coverage report \
  --include="ci/*" --fail-under=90) || status=$?

jq -rn --slurpfile fe "$fe" --slurpfile be "$be" --slurpfile ci "$ci" \
  -f "$root/scripts/coverage-tree.jq" || status=$?

exit "$status"
