#!/usr/bin/env bash
set -euo pipefail
manifest="$RUNNER_TEMP/flaky-tests-manifest.json"
output="$RUNNER_TEMP/flaky-tests-output"
uv run --locked python -m monori.ci.lib.flaky_tests --base "$BASE" --manifest "$manifest" --github-output "$output"
uv run --locked python -c \
  'import sys; from pathlib import Path; from monori.ci.quality_graph.checks.flaky_tests import execute_manifest; raise SystemExit(any(result.unstable for result in execute_manifest(Path(sys.argv[1]))))' \
  "$manifest"
