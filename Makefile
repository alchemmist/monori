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

# Manual rollout of exactly the revision this command is run on: dispatches the
# Deploy workflow with the current HEAD, so the SSH secrets live only in GitHub.
# Needs the gh CLI authenticated; the revision must already be on origin/main.
deploy:
	@rev=$$(git rev-parse HEAD); \
	git fetch -q origin; \
	git merge-base --is-ancestor "$$rev" origin/main || \
		{ echo "revision $$rev is not on origin/main — push it first"; exit 1; }; \
	echo "dispatching Deploy for $$rev"; \
	gh workflow run deploy.yaml --ref main -f sha="$$rev"; \
	echo "follow it with: gh run watch \$$(gh run list --workflow deploy.yaml -L1 --json databaseId -q '.[0].databaseId')"

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
	cd web && npm audit --audit-level=high --json | python3 ../scripts/npm-audit-gate.py

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
