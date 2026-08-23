#!/usr/bin/env bash
set -euo pipefail

SHFMT_VERSION=3.10.0
HADOLINT_VERSION=2.12.0
ACTIONLINT_VERSION=1.7.7
GITLEAKS_VERSION=8.21.2
LYCHEE_VERSION=0.24.2

bindir="${MONORI_TOOLS_BIN:-$HOME/.local/bin}"
mkdir -p "$bindir"

kernel=$(uname -s)
machine=$(uname -m)

case "$kernel" in
Darwin) goos=darwin ;;
Linux) goos=linux ;;
*)
  echo "unsupported OS: $kernel — install shfmt hadolint actionlint gitleaks manually" >&2
  exit 1
  ;;
esac

case "$machine" in
x86_64 | amd64) goarch=amd64 ;;
arm64 | aarch64) goarch=arm64 ;;
*)
  echo "unsupported arch: $machine" >&2
  exit 1
  ;;
esac

have() { command -v "$1" >/dev/null 2>&1; }

if ! have uv; then
  echo "uv not found — install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

have semgrep || uv tool install semgrep
have shellcheck || uv tool install shellcheck-py

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if ! have shfmt; then
  echo "installing shfmt ${SHFMT_VERSION}"
  curl -sSfL "https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/shfmt_v${SHFMT_VERSION}_${goos}_${goarch}" -o "$tmp/shfmt"
  install -m 0755 "$tmp/shfmt" "$bindir/shfmt"
fi

if ! have actionlint; then
  echo "installing actionlint ${ACTIONLINT_VERSION}"
  curl -sSfL "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_${goos}_${goarch}.tar.gz" -o "$tmp/actionlint.tgz"
  tar -xzf "$tmp/actionlint.tgz" -C "$tmp" actionlint
  install -m 0755 "$tmp/actionlint" "$bindir/actionlint"
fi

if ! have gitleaks; then
  echo "installing gitleaks ${GITLEAKS_VERSION}"
  case "$goarch" in
  amd64) gl_arch=x64 ;;
  arm64) gl_arch=arm64 ;;
  esac
  curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_${goos}_${gl_arch}.tar.gz" -o "$tmp/gitleaks.tgz"
  tar -xzf "$tmp/gitleaks.tgz" -C "$tmp" gitleaks
  install -m 0755 "$tmp/gitleaks" "$bindir/gitleaks"
fi

if ! have hadolint; then
  echo "installing hadolint ${HADOLINT_VERSION}"
  if [ "$kernel" = Darwin ]; then
    hmachine=x86_64
  elif [ "$goarch" = arm64 ]; then
    hmachine=arm64
  else
    hmachine=x86_64
  fi
  curl -sSfL "https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}/hadolint-${kernel}-${hmachine}" -o "$tmp/hadolint"
  install -m 0755 "$tmp/hadolint" "$bindir/hadolint"
fi

if ! have lychee; then
  echo "installing lychee ${LYCHEE_VERSION}"
  case "$goos-$goarch" in
  darwin-amd64)
    lychee_target=x86_64-apple-darwin
    lychee_sha256=887503a9cff667d322b8d0892b40bf49976eb9507af8483220a3706cdad55978
    ;;
  darwin-arm64)
    lychee_target=aarch64-apple-darwin
    lychee_sha256=c9d3740ea2d891854d37116c9fba840f37b6e7c89d330e7db84ac333631c4977
    ;;
  linux-amd64)
    lychee_target=x86_64-unknown-linux-gnu
    lychee_sha256=1f4e0ef7f6554a6ed33dd7ac144fb2e1bbed98598e7af973042fc5cd43951c9a
    ;;
  linux-arm64)
    lychee_target=aarch64-unknown-linux-gnu
    lychee_sha256=91a7bd65685da41b90ccb9bc867a3d649a7818042dae04ff405e55a25bddee4c
    ;;
  *)
    echo "unsupported lychee target: $goos-$goarch" >&2
    exit 1
    ;;
  esac
  archive="lychee-${lychee_target}.tar.gz"
  curl -sSfL "https://github.com/lycheeverse/lychee/releases/download/lychee-v${LYCHEE_VERSION}/${archive}" -o "$tmp/lychee.tgz"
  actual_sha256=$(python3 -c 'import hashlib, pathlib, sys; print(hashlib.file_digest(pathlib.Path(sys.argv[1]).open("rb"), "sha256").hexdigest())' "$tmp/lychee.tgz")
  if [ "$actual_sha256" != "$lychee_sha256" ]; then
    echo "lychee archive checksum mismatch" >&2
    exit 1
  fi
  tar -xzf "$tmp/lychee.tgz" -C "$tmp" --strip-components=1 "lychee-${lychee_target}/lychee"
  install -m 0755 "$tmp/lychee" "$bindir/lychee"
fi

case ":$PATH:" in
*":$bindir:"*) ;;
*) echo "note: add $bindir to your PATH so the installed tools resolve" >&2 ;;
esac
