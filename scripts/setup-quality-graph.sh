#!/usr/bin/env bash
set -euo pipefail
npm install --global npm@10.9.2
npm install --no-audit --no-fund --prefix web
npm install --no-audit --no-fund --prefix tools/frontend-perf
uv sync --all-groups
