#!/usr/bin/env bash
set -euo pipefail
manifest="$RUNNER_TEMP/flaky-tests-manifest.json"
output="$RUNNER_TEMP/flaky-tests-output"
uv run --locked python -m monori.ci.lib.flaky_tests --base "$BASE" --manifest "$manifest" --github-output "$output"
uv run --locked python -m monori.ci.quality_graph.checks.flaky_runner --manifest "$manifest"
