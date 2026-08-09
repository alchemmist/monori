#!/usr/bin/env bash
set -euo pipefail

script_dir=$(mktemp -d)
trap 'rm -r "$script_dir"' EXIT

uv run --locked --group lint python -m monori.ci.lib.workflow_shellcheck \
  --output "$script_dir" "$@"

status=0
for script in "$script_dir"/*.sh; do
  if ! shellcheck --norc --external-sources --shell bash \
    --exclude SC1091,SC2194,SC2050,SC2153,SC2154,SC2157,SC2043 "$script"; then
    status=1
  fi
done
exit "$status"
