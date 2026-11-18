#!/usr/bin/env bash
set -euo pipefail
npm install --global npm@10.9.2
npm ci --no-audit --no-fund --prefix web
npm ci --no-audit --no-fund --prefix tools/frontend-perf
uv sync --locked --all-groups
