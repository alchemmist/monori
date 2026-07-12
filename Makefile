API_PORT ?= 8077
COMPOSE ?= $(shell command -v docker >/dev/null 2>&1 && echo "docker compose" || echo "podman compose")

WEBBIN := web/node_modules/.bin

.PHONY: dev down api web build \
        fmt fmt-check \
        lint lint-web lint-css lint-html lint-server lint-yaml lint-md lint-actions lint-docker lint-shell spell \
        typecheck analyze audit audit-deps audit-secrets \
        test t-fast t-medium t-slow coverage mutation \
        check help

up:
	$(COMPOSE) -f deploy/docker-compose.dev.yml up --build

down:
	$(COMPOSE) -f deploy/docker-compose.dev.yml down

api:
	cd server && uv run uvicorn app.main:app --port $(API_PORT) --reload

web:
	cd web && API_PORT=$(API_PORT) npm run dev

build:
	cd web && npm run build
	rm -rf server/static
	cp -r web/dist server/static

fmt:
	$(WEBBIN)/prettier --write .
	cd server && uv run ruff format . && uv run ruff check . --fix

fmt-check:
	$(WEBBIN)/prettier --check .
	cd server && uv run ruff format --check .

lint: lint-web lint-css lint-html lint-server lint-yaml lint-md lint-actions lint-docker lint-shell spell

lint-web:
	cd web && npm run --silent lint

lint-css:
	$(WEBBIN)/stylelint "web/src/**/*.css"

lint-html:
	$(WEBBIN)/htmlhint web/index.html

lint-server:
	cd server && uv run ruff check .

lint-yaml:
	uvx yamllint -c .yamllint.yaml .

lint-md:
	$(WEBBIN)/markdownlint-cli2

lint-actions:
	actionlint

lint-docker:
	hadolint deploy/Dockerfile

lint-shell:
	@files=$$(git ls-files '*.sh'); [ -z "$$files" ] || shellcheck $$files
	@files=$$(git ls-files '*.sh'); [ -z "$$files" ] || shfmt -d $$files

spell:
	uvx codespell web/src server/app server/tests \
		server/export_snapshot.py server/migrate.py server/verify_parity.py \
		README.md web/README.md Makefile .github

typecheck:
	cd server && uv run mypy

analyze:
	cd server && uv run bandit -c pyproject.toml -q -r app
	semgrep --error --quiet --config p/python --config p/javascript \
		--exclude-rule python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 .

audit: audit-deps audit-secrets

audit-deps:
	cd web && npm audit --audit-level=high

audit-secrets:
	gitleaks detect --no-banner --redact

test: t-fast t-medium t-slow

t-fast:
	cd web && npx vitest run
	cd server && uv run pytest -q -m "not integration"

t-medium:
	cd server && uv run pytest -q -m integration

t-slow:
	@echo "e2e (Playwright) not implemented yet — see #42 rollout phase 6"

coverage:
	cd web && npx vitest run --coverage
	cd server && uv run pytest -q --cov

mutation:
	$(WEBBIN)/stryker run
	cd server && mutmut run

check: fmt-check lint typecheck analyze test

help:
	@echo "run:      dev down api web build"
	@echo "format:   fmt fmt-check"
	@echo "lint:     lint (web css html server yaml md actions docker shell spell)"
	@echo "static:   typecheck analyze audit"
	@echo "test:     test t-fast t-medium t-slow coverage mutation"
	@echo "gate:     check"
