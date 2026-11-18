#!/usr/bin/env bash
set -euo pipefail

HADOLINT_VERSION=2.12.0
HADOLINT_SHA256=56de6d5e5ec427e17b74fa48d51271c7fc0d61244bf5c90e828aab8362d55010
ACTIONLINT_VERSION=1.7.7
SHFMT_VERSION=3.10.0

sudo apt-get update
sudo apt-get install -y shellcheck

shfmt_bin="shfmt_v${SHFMT_VERSION}_linux_amd64"
curl -sSfL "https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/${shfmt_bin}" -o "${shfmt_bin}"
curl -sSfL "https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/sha256sums.txt" -o shfmt_sha256sums.txt
grep " ${shfmt_bin}\$" shfmt_sha256sums.txt | sha256sum -c -
sudo install -m 0755 "${shfmt_bin}" /usr/local/bin/shfmt

curl -sSfL "https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}/hadolint-Linux-x86_64" -o hadolint
echo "${HADOLINT_SHA256}  hadolint" | sha256sum -c -
sudo install -m 0755 hadolint /usr/local/bin/hadolint

tarball="actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz"
curl -sSfL "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/${tarball}" -o "${tarball}"
curl -sSfL "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_checksums.txt" -o actionlint_checksums.txt
grep " ${tarball}\$" actionlint_checksums.txt | sha256sum -c -
tar -xzf "${tarball}" actionlint
sudo install -m 0755 actionlint /usr/local/bin/actionlint
