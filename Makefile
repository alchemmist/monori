API_PORT ?= 8077
COMPOSE ?= $(shell command -v docker >/dev/null 2>&1 && echo "docker compose" || echo "podman compose")
MUTATION_THRESHOLD ?= 85

WEBBIN := web/node_modules/.bin

.PHONY: dev down deploy api web build \
        fmt fmt-check \
        lint lint-web lint-css lint-html lint-server lint-sql lint-yaml lint-md lint-actions lint-docker lint-shell spell \
        typecheck analyze audit audit-deps audit-deps-py audit-secrets \
        test t-fast t-medium t-slow coverage mutation \
        check

up:
	$(COMPOSE) -f deploy/docker-compose.dev.yml up --build

down:
	$(COMPOSE) -f deploy/docker-compose.dev.yml down

# Manual rollout of exactly the revision this command is run on (mirrors the
# Deploy workflow). Reads SSH_HOST, SSH_USER and SSH_PROJECT_PATH from a .env
# file in the repo root (falling back to the environment); the revision must
# already be pushed so the server can fetch it.
deploy:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	: "$${SSH_HOST:?set SSH_HOST in .env or the environment}"; \
	: "$${SSH_USER:?set SSH_USER in .env or the environment}"; \
	: "$${SSH_PROJECT_PATH:?set SSH_PROJECT_PATH in .env or the environment}"; \
	rev=$$(git rev-parse HEAD); \
	git fetch -q origin; \
	git branch -r --contains "$$rev" | grep -q . || \
		{ echo "revision $$rev is not on origin — push it first"; exit 1; }; \
	echo "deploying $$rev to $$SSH_HOST"; \
	ssh "$$SSH_USER@$$SSH_HOST" "set -e; cd '$$SSH_PROJECT_PATH'; \
		git fetch origin; git checkout --detach $$rev; \
		cd deploy; docker compose up --build -d"

api:
	cd server && uv run uvicorn app.main:app --port $(API_PORT) --reload

web:
	cd web && API_PORT=$(API_PORT) npm run dev

build:
	cd web && npm run build
	rm -rf server/static
	cp -r web/dist server/static

SQLFLUFF := uvx --from 'sqlfluff==3.4.2' sqlfluff

fmt:
	$(WEBBIN)/prettier --write .
	cd server && uv run ruff format . && uv run ruff check . --fix
	$(SQLFLUFF) fix -f server/schema.sql

fmt-check:
	$(WEBBIN)/prettier --check .
	cd server && uv run ruff format --check .
	$(SQLFLUFF) lint server/schema.sql

lint: lint-web lint-css lint-html lint-server lint-sql lint-yaml lint-md lint-actions lint-docker lint-shell spell

lint-web:
	cd web && npm run --silent lint

lint-css:
	$(WEBBIN)/stylelint --config web/.stylelintrc.json "web/src/**/*.css"

lint-html:
	$(WEBBIN)/htmlhint web/index.html

lint-server:
	cd server && uv run ruff check .

lint-sql:
	$(SQLFLUFF) lint server/schema.sql

lint-yaml:
	uvx yamllint -c .yamllint.yaml .

lint-md:
	$(WEBBIN)/markdownlint-cli2

lint-actions:
	actionlint

lint-docker:
	hadolint deploy/Dockerfile.front deploy/Dockerfile.back deploy/Dockerfile.sync deploy/Dockerfile.dev

lint-shell:
	@files=$$(git ls-files '*.sh'); [ -z "$$files" ] || shellcheck $$files
	@files=$$(git ls-files '*.sh'); [ -z "$$files" ] || shfmt -d $$files

spell:
	uvx codespell web/src server/app server/tests \
		server/export_snapshot.py server/migrate.py server/verify_parity.py \
		README.md web/README.md docs Makefile .github

typecheck:
	cd server && uv run mypy

analyze:
	cd server && uv run bandit -c pyproject.toml -q -r app
	semgrep --error --quiet --config p/python --config p/javascript \
		--exclude-rule python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 .

audit: audit-deps audit-deps-py audit-secrets

audit-deps:
	cd web && npm audit --audit-level=high

audit-deps-py:
	cd server && uv export --no-dev --no-hashes --format requirements-txt | uv run pip-audit -r /dev/stdin

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
	bash scripts/coverage-tree.sh

mutation:
	@thr=$(MUTATION_THRESHOLD); \
	( cd web && MUTATION_THRESHOLD=$$thr npx stryker run ); web=$$?; \
	( cd server && { uv run mutmut run || true; } && mkdir -p mutants && uv run mutmut export-cicd-stats ); \
	python3 scripts/mutation-gate.py server/mutants/mutmut-cicd-stats.json $$thr; srv=$$?; \
	echo "── mutation gates (threshold $$thr%): stryker exit=$$web, mutmut gate exit=$$srv ──"; \
	[ $$web -eq 0 ] && [ $$srv -eq 0 ]

check: fmt-check lint typecheck analyze test
