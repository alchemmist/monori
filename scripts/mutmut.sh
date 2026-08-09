#!/usr/bin/env bash
set -euo pipefail

repository=$PWD
workspace=$(mktemp -d)
trap 'rm -rf "$workspace"' EXIT

mkdir -p "$workspace/monori/ci" "$workspace/monori/server" "$workspace/server" "$workspace/ci"
cp -R common "$workspace/monori/common"
cp -R ci/lib "$workspace/monori/ci/lib"
cp -R ci/quality_graph "$workspace/monori/ci/quality_graph"
cp ci/__init__.py "$workspace/monori/ci/__init__.py"
cp -R server/app "$workspace/monori/server/app"
cp -R server/migrations "$workspace/monori/server/migrations"
cp server/__init__.py server/schema.sql "$workspace/monori/server/"
cp -R server/tests "$workspace/server/tests"
cp -R ci/tests "$workspace/ci/tests"
cp -R .github "$workspace/.github"
cp -R scripts "$workspace/scripts"
cp Makefile "$workspace/Makefile"
cp pyproject.toml "$workspace/pyproject.toml"

if [ -d mutants ]; then
  cp -R mutants "$workspace/mutants"
fi

set +e
(cd "$workspace" && env -u GITHUB_STEP_SUMMARY -u MUTATION_SUMMARY_PATH "$repository/.venv/bin/mutmut" "$@")
status=$?
set -e

if [ -d "$workspace/mutants" ]; then
  replacement="$repository/mutants.replacement"
  rm -rf "$replacement"
  mv "$workspace/mutants" "$replacement"
  rm -rf "$repository/mutants"
  mv "$replacement" "$repository/mutants"
fi

exit "$status"
