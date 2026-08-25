#!/usr/bin/env bash
set -euo pipefail

LYCHEE_VERSION=0.24.2
LYCHEE_SHA256=1f4e0ef7f6554a6ed33dd7ac144fb2e1bbed98598e7af973042fc5cd43951c9a
archive=lychee-x86_64-unknown-linux-gnu.tar.gz

curl --connect-timeout 10 --max-time 120 --retry 3 --retry-max-time 120 -sSfL \
  "https://github.com/lycheeverse/lychee/releases/download/lychee-v${LYCHEE_VERSION}/${archive}" \
  -o "$RUNNER_TEMP/lychee.tgz"
echo "${LYCHEE_SHA256}  $RUNNER_TEMP/lychee.tgz" | sha256sum -c -
tar -xzf "$RUNNER_TEMP/lychee.tgz" -C "$RUNNER_TEMP" --strip-components=1 \
  "lychee-x86_64-unknown-linux-gnu/lychee"
sudo install -m 0755 "$RUNNER_TEMP/lychee" /usr/local/bin/lychee
