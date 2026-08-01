API_PORT ?= 8077
HAVE_DOCKER_COMPOSE = $(shell docker compose version >/dev/null 2>&1 && echo 1)
HAVE_PODMAN_COMPOSE = $(shell podman compose version >/dev/null 2>&1 && echo 1)
COMPOSE ?= $(if $(HAVE_DOCKER_COMPOSE),docker compose,$(if $(HAVE_PODMAN_COMPOSE),podman compose --in-pod=false,docker compose))
MUTATION_THRESHOLD ?= 85

WEBBIN := web/node_modules/.bin

.DEFAULT_GOAL := up

.PHONY: install setup tools dev down reset-db deploy api web build \
        fmt fmt-check \
        lint lint-web lint-css lint-html lint-server lint-sql lint-yaml lint-md lint-docs lint-actions lint-docker lint-shell spell \
        type type-front type-back analyze audit audit-deps audit-deps-py audit-secrets \
        test t-fast t-medium t-slow t-slow-ui coverage mutation m-front m-front-file m-back \
        schema-diagram check

install:
	cd web && npm install --no-audit --no-fund
	cd server && uv sync
	$(MAKE) tools

setup: install

tools:
	bash scripts/install-tools.sh
	uvx --from 'sqlfluff==3.4.2' sqlfluff --version >/dev/null
	uvx yamllint --version >/dev/null
	uvx codespell --version >/dev/null

up:
	$(COMPOSE) -f deploy/docker-compose.dev.yml up --build

down:
	$(COMPOSE) -f deploy/docker-compose.dev.yml down

reset-db:
	rm -f server/data/monori.db server/data/monori.db-wal server/data/monori.db-shm

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

schema-diagram:
	python3 scripts/gen_schema_diagram.py

fmt: schema-diagram
	$(WEBBIN)/prettier --write .
	@(uv run --project server ruff check --config server/pyproject.toml . --fix >/dev/null 2>&1 || true)
	uv run --project server ruff format --config server/pyproject.toml .
	$(SQLFLUFF) fix .
	@-$(WEBBIN)/markdownlint-cli2 --fix >/dev/null 2>&1
	@files=$$(git ls-files '*.sh'); [ -z "$$files" ] || shfmt -w $$files

fmt-check:
	$(WEBBIN)/prettier --check .
	uv run --project server ruff check --config server/pyproject.toml .
	uv run --project server ruff format --config server/pyproject.toml --check .
	$(SQLFLUFF) lint .

lint: lint-web lint-css lint-html lint-server lint-sql lint-yaml lint-md lint-docs lint-actions lint-docker lint-shell spell

lint-web:
	cd web && npm run --silent lint

lint-css:
	$(WEBBIN)/stylelint --config web/.stylelintrc.json "web/src/**/*.css"

lint-html:
	$(WEBBIN)/htmlhint web/index.html

lint-server:
	uv run --project server ruff check --config server/pyproject.toml .

lint-sql:
	$(SQLFLUFF) lint .

lint-yaml:
	uvx yamllint -c .yamllint.yaml .

lint-md:
	$(WEBBIN)/markdownlint-cli2

lint-docs:
	python3 scripts/gen_schema_diagram.py --check

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

type: type-back # type-front

type-front:
	cd web && npm run --silent typecheck

type-back:
	@set +e; \
	MYPYPATH=server uv run --project server --extra connectors mypy --config-file server/pyproject.toml --strict .; py=$$?; \
	echo "type-back: python=$$py"; \
	test $$py -eq 0

analyze:
	cd server && uv run bandit -c pyproject.toml -q -r app
	semgrep --error --quiet --config p/python --config p/javascript \
		--exclude-rule python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 .

audit: audit-deps audit-deps-py audit-secrets

audit-deps:
	cd web && npm install --no-audit --no-fund --silent
	(cd web && npm audit --audit-level=high --json) | \
		uv run --project server python scripts/npm-audit-gate.py

audit-deps-py:
	@req=$$(mktemp); \
	( cd server && uv export --no-dev --no-hashes --format requirements-txt -o "$$req" \
		&& uv run pip-audit -r "$$req" ); code=$$?; \
	rm -f "$$req"; exit $$code

audit-secrets:
	gitleaks detect --no-banner --redact

test: t-fast t-medium t-slow

t-fast:
	cd web && npx vitest run
	cd server && uv run pytest -q -m "not integration"

t-medium:
	cd server && uv run pytest -q -m integration

t-slow:
	COMPOSE="$(COMPOSE)" bash scripts/e2e.sh

t-slow-ui:
	COMPOSE="$(COMPOSE)" bash scripts/e2e.sh --ui

coverage:
	bash scripts/coverage-tree.sh

m-front:
	@set +e; \
	thr=$(MUTATION_THRESHOLD); \
	echo "── stryker: building the per-test coverage map; mutation progress begins after this phase ──"; \
	( cd web && MUTATION_THRESHOLD=$$thr npx stryker run ); web=$$?; \
	node scripts/stryker-summary.mjs; \
	echo "── frontend mutation gate (threshold $$thr%): stryker exit=$$web ──"; \
	exit $$web

# mutate a single file for a quick, isolated read: `make m-front-file FILE=src/pages/DashboardPage.jsx`
# a throwaway incremental cache keeps the run fresh and leaves the shared report untouched
m-front-file:
	@if [ -z "$(FILE)" ]; then \
		echo "usage: make m-front-file FILE=src/pages/DashboardPage.jsx"; exit 2; \
	fi
	cd web && ./node_modules/.bin/stryker run --mutate "$(FILE)" --incrementalFile "$$(mktemp -u -t stryker-file.XXXXXX).json"

m-back:
	@set +e; \
	thr=$(MUTATION_THRESHOLD); \
	( cd server && mkdir -p mutants && uv run mutmut run 2>mutants/mutmut-stderr.log ); mutmut=$$?; \
	( cd server && mkdir -p mutants && uv run mutmut export-cicd-stats ); export=$$?; \
	if [ $$export -eq 0 ]; then \
		python3 scripts/mutation-gate.py server/mutants/mutmut-cicd-stats.json $$thr; srv=$$?; \
	else \
		srv=$$export; \
	fi; \
	if [ -s server/mutants/mutmut-stderr.log ]; then echo "── mutmut diagnostics: server/mutants/mutmut-stderr.log ──"; fi; \
	echo "── backend mutation gate (threshold $$thr%): mutmut run exit=$$mutmut, mutmut gate exit=$$srv ──"; \
	if [ $$mutmut -ne 0 ] || [ $$srv -ne 0 ]; then exit 1; fi

mutation:
	@set +e; \
	$(MAKE) MUTATION_THRESHOLD=$(MUTATION_THRESHOLD) m-front; front=$$?; \
	$(MAKE) MUTATION_THRESHOLD=$(MUTATION_THRESHOLD) m-back; back=$$?; \
	echo "── mutation gates: frontend exit=$$front, backend exit=$$back ──"; \
	if [ $$front -ne 0 ] || [ $$back -ne 0 ]; then exit 1; fi

check: fmt-check lint type analyze t-fast
