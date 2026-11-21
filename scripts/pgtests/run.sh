#!/usr/bin/env bash
# Requires local PG binaries on PATH. Never connects to a network database.
set -euo pipefail
cd "$(dirname "$0")/../.."
unset DATABASE_URL MONORI_DATABASE_URL PGHOST PGPORT PGSERVICE PGOPTIONS
export MONORI_TEST_CLUSTER
MONORI_TEST_CLUSTER=$(mktemp -d /tmp/monori-pgtests.XXXXXXXX)
cleanup() { pg_ctl -D "$MONORI_TEST_CLUSTER/db" stop -m fast >/dev/null || true; rm -rf -- "$MONORI_TEST_CLUSTER"; }
trap cleanup EXIT
initdb -D "$MONORI_TEST_CLUSTER/db" --no-locale -E UTF8 >/dev/null
pg_ctl -D "$MONORI_TEST_CLUSTER/db" -l "$MONORI_TEST_CLUSTER/log" -o "-h '' -k $MONORI_TEST_CLUSTER -p 55442" start >/dev/null
createdb -h "$MONORI_TEST_CLUSTER" -p 55442 monori_test
PYTHONPATH="$PWD/scripts/pgtests${PYTHONPATH:+:$PYTHONPATH}" uv run --group test pytest -p monori_pg_testplugin -q server/tests/integration --ignore=server/tests/integration/test_admin_sql.py "$@"
