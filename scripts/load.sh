#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE=${COMPOSE:-"docker compose"}
LOAD_TARGET=${1:-api}
LOAD_LEVELS=${LOAD_LEVELS:-"10 25 50"}
LOAD_DURATION=${LOAD_DURATION:-30s}
LOAD_OUTPUT_DIR=${LOAD_OUTPUT_DIR:-"$PWD/reports/perf"}
MONORI_SQLITE_JOURNAL_MODE=${MONORI_SQLITE_JOURNAL_MODE:-DELETE}
export MONORI_SQLITE_JOURNAL_MODE
export CONTAINER_PLATFORM=${CONTAINER_PLATFORM:-"linux/$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"}
export PERF_K6_DIR="$PWD/performance/k6"
export PERF_RESULTS_DIR="$LOAD_OUTPUT_DIR"

case "$LOAD_OUTPUT_DIR" in
"" | "/" | "$PWD")
  echo "load: refusing unsafe LOAD_OUTPUT_DIR '$LOAD_OUTPUT_DIR'" >&2
  exit 2
  ;;
esac

case "$LOAD_TARGET" in
api) workloads="auth read write import" ;;
auth | read | write | import) workloads=$LOAD_TARGET ;;
e2e) workloads="e2e" ;;
*)
  echo "usage: scripts/load.sh [api|auth|read|write|import|e2e]" >&2
  exit 2
  ;;
esac

mkdir -p "$LOAD_OUTPUT_DIR"
journal_project=$(printf '%s' "$MONORI_SQLITE_JOURNAL_MODE" | tr '[:upper:]' '[:lower:]')
project="monori-load-$journal_project-$$"
compose_files=(-f deploy/docker-compose.test.yml -f deploy/docker-compose.perf.yml -p "$project")

stack() {
  read -r -a command <<<"$COMPOSE"
  "${command[@]}" "${compose_files[@]}" "$@"
}

trap 'stack down --volumes --remove-orphans >/dev/null 2>&1 || true' EXIT

base_url="http://localhost:${E2E_PORT:-8078}"

wait_for_stack() {
  ready=""
  for _ in $(seq 1 180); do
    if curl -fsS --connect-timeout 1 --max-time 2 "$base_url/openapi.json" >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done
  if [ -z "$ready" ]; then
    stack logs
    return 1
  fi
}

stack up --build --detach back front
wait_for_stack

capture_resources() {
  output=$1
  while :; do
    stats=$(stack stats --no-stream --format json back front 2>/dev/null) || stats=""
    case "$stats" in
    "") stats="[]" ;;
    \[*\]) ;;
    *) stats="[$(printf '%s\n' "$stats" | paste -sd, -)]" ;;
    esac
    stats=$(printf '%s' "$stats" | tr -d '\r\n')
    printf '{"sampled_at":%s,"containers":%s}\n' "$(date +%s)" "$stats" >>"$output"
    sleep 1
  done
}

run_level() {
  workload=$1
  level=$2
  stack up --detach back front >/dev/null
  stack restart front >/dev/null
  wait_for_stack
  script=/scripts/api.js
  [ "$workload" = e2e ] && script=/scripts/journey.js
  name="$MONORI_SQLITE_JOURNAL_MODE-$workload-$level"
  resources="$LOAD_OUTPUT_DIR/$name-resources.jsonl"
  : >"$resources"
  capture_resources "$resources" &
  sampler=$!
  set +e
  stack run --rm --no-deps --user "$(id -u):$(id -g)" \
    -e WORKLOAD="$workload" \
    -e VUS="$level" \
    -e DURATION="$LOAD_DURATION" \
    k6 run --summary-export="/results/$name.json" "$script" \
    2>&1 | tee "$LOAD_OUTPUT_DIR/$name.log"
  result=${PIPESTATUS[0]}
  set -e
  kill "$sampler" >/dev/null 2>&1 || true
  wait "$sampler" >/dev/null 2>&1 || true
  return "$result"
}

failed=0
for workload in $workloads; do
  for level in $LOAD_LEVELS; do
    run_level "$workload" "$level" || failed=1
  done
done

uv run --locked python performance/report.py --input "$LOAD_OUTPUT_DIR" --output "$LOAD_OUTPUT_DIR/summary.md"
exit "$failed"
