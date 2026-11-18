# Contributing

## Development environment

The dev toolchain is set up for **Ubuntu** (24.04 or newer — it ships Python
3.12, which the server requires). On Windows, work inside **WSL** with an Ubuntu
distribution; on other Linux distros you will have to adapt the package names
and repositories yourself.

Open a terminal (WSL on Windows) and run this one command to prepare the whole
environment — base tools, Node 22, `uv`, and the linters that `make check`
needs but that are not in the Ubuntu repositories:

```sh
sudo apt-get update && \
sudo apt-get upgrade -y && \
sudo apt-get install -y \
  make git curl ca-certificates build-essential jq \
  python3 python3-venv python3-pip \
  podman \
  shellcheck vim zip unzip htop zsh && \
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash - && \
sudo apt-get install -y nodejs && \
sudo npm install -g npm@latest && \
sudo npm install -g @anthropic-ai/claude-code @openai/codex && \
curl -LsSf https://astral.sh/uv/install.sh | sh && \
export PATH="$HOME/.local/bin:$PATH" && \
uv tool install semgrep && \
uv tool install podman-compose && \
sudo curl -fsSL -o /usr/local/bin/hadolint \
  https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 && \
sudo chmod +x /usr/local/bin/hadolint && \
bash <(curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash) && \
sudo mv actionlint /usr/local/bin/ && \
```

Notes:

- The rest of the linters and formatters (`ruff`, `mypy`, `bandit`, `sqlfluff`,
  `yamllint`, `codespell`, `pip-audit`, `prettier`, `stylelint`, `markdownlint`,
  `htmlhint`) are pulled in automatically by `uv` and `npm` when you run the
  `make` targets, so you don't install them by hand.
- `gitleaks` and `shfmt` are not in apt either; grab their release binaries from
  GitHub if you want `make audit-secrets` and `make lint-shell` to pass locally.
- Just running the app (`make up`, or `make api` + `make web`) needs only `uv`,
  Node, `make`, and `podman` + `podman-compose`. The extra linters matter only
  for the full `make check`.

## Troubleshooting

**apt says `Temporary failure resolving 'archive.ubuntu.com'` / packages have
"no installation candidate".** This is broken DNS inside WSL, not a missing
package — apt can't download the repository indexes, so every package looks
absent. Fix the resolver, then re-run the setup command:

```sh
printf '[network]\ngenerateResolvConf = false\n' | sudo tee /etc/wsl.conf
sudo rm -f /etc/resolv.conf
sudo tee /etc/resolv.conf >/dev/null <<'EOF'
nameserver 8.8.8.8
nameserver 1.1.1.1
EOF
sudo chattr +i /etc/resolv.conf   # stop WSL from regenerating it
```

Then run `wsl --shutdown` from Windows PowerShell, reopen WSL, and confirm with
`getent hosts archive.ubuntu.com` (it should print an IP).
