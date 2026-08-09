API_PORT ?= 8077
HAVE_DOCKER_COMPOSE = $(shell docker compose version >/dev/null 2>&1 && echo 1)
HAVE_PODMAN_COMPOSE = $(shell podman compose version >/dev/null 2>&1 && echo 1)
COMPOSE ?= $(if $(HAVE_DOCKER_COMPOSE),docker compose,$(if $(HAVE_PODMAN_COMPOSE),podman compose --in-pod=false,docker compose))
MUTATION_THRESHOLD ?= 85
MUTATION_DIFF_THRESHOLD ?= 90
MUTATION_JOBS ?= $(shell getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
BASE ?= origin/main
MONORI_TOOLS_BIN ?= $(HOME)/.local/bin

WEBBIN := web/node_modules/.bin
PYTHON_SOURCES := $(shell python3 -c 'import tomllib; from pathlib import Path; print(*tomllib.loads(Path("pyproject.toml").read_text())["tool"]["uv"]["workspace"]["members"])')
CLOC_EXCLUDE_DIRS := .git,.worktrees,.claude,node_modules,.venv,__pycache__,.pytest_cache,.mypy_cache,.ruff_cache,dist,static,data,reports,coverage,htmlcov,.stryker-tmp,.mutmut-cache,mutants,playwright-report,test-results

.DEFAULT_GOAL := up

.PHONY: install setup tools dev down reset-db deploy api web build clean \
        code-stat \
        precommit-install precommit-uninstall \
        fmt fmt-check \
        lint lint-web lint-css lint-html lint-server lint-no-comments lint-sql lint-yaml lint-md lint-docs lint-actions lint-docker lint-shell spell \
        type type-front type-back analyze analyze-python-dead-code analyze-javascript-dead-code audit audit-deps audit-deps-py audit-secrets \
        test t-workflow t-fast t-medium t-ci t-ci-unit t-ci-integration t-slow t-slow-ui t-front t-back t-e2e t-e2e-ui coverage perf-front-diff mutation mutation-diff mutation-python m-front m-front-diff m-front-file m-back m-back-diff \
        schema-diagram check

install:
	cd web && npm install --no-audit --no-fund
	cd tools/frontend-perf && npm install --no-audit --no-fund
	uv sync --locked --all-groups
	@if ! command -v cloc >/dev/null 2>&1; then \
		sudo apt-get update && sudo apt-get install -y cloc; \
	fi
	$(MAKE) tools

setup: install

tools:
	MONORI_TOOLS_BIN="$(MONORI_TOOLS_BIN)" bash scripts/install-tools.sh
	uvx --from 'sqlfluff==3.4.2' sqlfluff --version >/dev/null
	uvx yamllint --version >/dev/null
	uvx codespell --version >/dev/null

precommit-install:
	@hook=$$(git rev-parse --git-path hooks)/pre-commit; \
	if [ -e "$$hook" ] && ! grep -q '^# monori-pre-commit-hook$$' "$$hook"; then \
		echo "Refusing to replace an existing non-Monori hook: $$hook"; \
		exit 1; \
	fi; \
	install -m 755 scripts/pre-commit "$$hook"; \
	echo "Installed Monori pre-commit hook at $$hook"

precommit-uninstall:
	@hook=$$(git rev-parse --git-path hooks)/pre-commit; \
	if [ -e "$$hook" ] && grep -q '^# monori-pre-commit-hook$$' "$$hook"; then \
		rm -- "$$hook"; \
		echo "Removed Monori pre-commit hook from $$hook"; \
	else \
		echo "Monori pre-commit hook is not installed"; \
	fi

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
	uv run --locked --group runtime uvicorn monori.server.app.main:app --port $(API_PORT) --reload

web:
	cd web && API_PORT=$(API_PORT) npm run dev

build:
	cd web && npm run build
	rm -rf server/static
	cp -r web/dist server/static

clean:
	@root=$$(git rev-parse --show-toplevel); \
	remove_path() { \
		path="$$1"; \
		[ -e "$$path" ] || [ -L "$$path" ] || return 0; \
		resolved=$$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$$path") || return 1; \
		case "$$resolved" in \
			"$$root"/*) rm -rf -- "$$path" ;; \
			*) echo "Skipping path outside repository: $$path" ;; \
		esac; \
	}; \
	for path in \
		.coverage coverage.json htmlcov coverage \
		.stryker-tmp reports .mutmut-cache mutants \
		.issue197 server/static ci/coverage.json web/dist web/test-results web/playwright-report; do \
		remove_path "$$path"; \
	done
	find . \
		-path './.git' -prune -o \
		-path './web/node_modules' -prune -o \
		-path './.venv' -prune -o \
		-path './deploy/data' -prune -o \
		-path './.worktrees' -prune -o \
		-path './.claude/worktrees' -prune -o \
		-type d -name '__pycache__' -prune -exec rm -rf {} + -o \
		-type f -name '*.pyc' -delete

code-stat:
	cloc . --exclude-dir=$(CLOC_EXCLUDE_DIRS)

SQLFLUFF := uvx --from 'sqlfluff==3.4.2' sqlfluff

schema-diagram:
	python3 scripts/gen_schema_diagram.py

fmt: schema-diagram fmt-front fmt-back fmt-ci

fmt-front:
	$(WEBBIN)/prettier --write web

fmt-back:
	@(uv run --locked --group format ruff check server --fix >/dev/null 2>&1 || true)
	uv run --locked --group format ruff format server
	$(SQLFLUFF) fix server

fmt-ci:
	@files=$$(git ls-files '*.cjs' '*.css' '*.html' '*.json' '*.jsonc' '*.md' '*.mjs' '*.ts' '*.tsx' '*.yaml' '*.yml' | grep -Ev '^(web|server)/'); [ -z "$$files" ] || $(WEBBIN)/prettier --write $$files
	@(uv run --locked --group format ruff check common ci --fix >/dev/null 2>&1 || true)
	uv run --locked --group format ruff format common ci
	@-$(WEBBIN)/markdownlint-cli2 --fix >/dev/null 2>&1
	@files=$$(git ls-files '*.sh'); [ -z "$$files" ] || shfmt -w $$files

fmt-check:
	@files=$$(git ls-files '*.cjs' '*.css' '*.html' '*.json' '*.jsonc' '*.md' '*.mjs' '*.ts' '*.tsx' '*.yaml' '*.yml'); [ -z "$$files" ] || $(WEBBIN)/prettier --check $$files
	uv run --locked --group format ruff check $(PYTHON_SOURCES)
	uv run --locked --group format ruff format --check $(PYTHON_SOURCES)
	$(SQLFLUFF) lint .

lint: lint-web lint-css lint-html lint-server lint-sql lint-yaml lint-md lint-docs lint-actions lint-docker lint-shell spell

lint-web:
	cd web && ./node_modules/.bin/oxlint
	cd web && ./node_modules/.bin/eslint "src/**/*.{ts,tsx}" "e2e/**/*.ts" "*.config.ts" stryker.conf.ts

lint-css:
	$(WEBBIN)/stylelint --config web/.stylelintrc.json "web/src/**/*.css"

lint-html:
	$(WEBBIN)/htmlhint web/index.html

lint-server: lint-no-comments
	uv run --locked --group lint ruff check $(PYTHON_SOURCES)

lint-no-comments:
	uv run --locked --group lint python -m monori.ci.lib.no_comments $(PYTHON_SOURCES)

lint-sql:
	$(SQLFLUFF) lint .

lint-yaml:
	uvx yamllint -c .yamllint.yaml .

lint-md:
	$(WEBBIN)/markdownlint-cli2

lint-docs:
	python3 scripts/gen_schema_diagram.py --check

lint-actions:
	actionlint -shellcheck=
	scripts/workflow-shellcheck.sh \
		.github/workflows/*.yaml .github/actions/*/action.yml

lint-docker:
	hadolint deploy/Dockerfile.front deploy/Dockerfile.back deploy/Dockerfile.sync deploy/Dockerfile.dev ci/testkit/Dockerfile

lint-shell:
	@files=$$(git ls-files '*.sh'); [ -z "$$files" ] || shellcheck $$files
	@files=$$(git ls-files '*.sh'); [ -z "$$files" ] || shfmt -d $$files

spell:
	uvx codespell --skip='*/mutants/*' web/src $(PYTHON_SOURCES) \
		README.md web/README.md docs Makefile .github

type: type-back type-front

type-front:
	cd web && ./node_modules/.bin/tsc --noEmit
	cd web && ./node_modules/.bin/oxlint --type-aware --report-unused-disable-directives --ignore-pattern eslint.config.mjs
	cd web && ./node_modules/.bin/eslint "src/**/*.{ts,tsx}" "e2e/**/*.ts" "*.config.ts" stryker.conf.ts

type-back:
	uv sync --locked --no-editable --reinstall-package monori-common --reinstall-package monori-ci --reinstall-package monori-server --group type
	UV_NO_SYNC=1 uv run --locked --group type mypy

analyze:
	uv run --locked --group analyze bandit -q -c pyproject.toml -r $(PYTHON_SOURCES)
	semgrep --error --quiet --config p/python --config p/javascript \
		--exclude-rule python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 .
	$(MAKE) analyze-python-dead-code analyze-javascript-dead-code

analyze-python-dead-code:
	uv run --locked --group analyze vulture

analyze-javascript-dead-code:
	cd web && ./node_modules/.bin/knip --no-progress

audit: audit-deps audit-deps-py audit-secrets

audit-deps:
	cd web && npm install --no-audit --no-fund --silent
	(cd web && npm audit --audit-level=high --json) | \
		uv run --locked --group audit python -m monori.ci.lib.npm_audit_gate
	cd tools/frontend-perf && npm install --no-audit --no-fund --silent
	(cd tools/frontend-perf && npm audit --audit-level=high --json) | \
		uv run --locked --group audit python -m monori.ci.lib.npm_audit_gate

audit-deps-py:
	@req=$$(mktemp); \
	( uv export --group runtime --no-dev --no-hashes --format requirements-txt -o "$$req" \
		&& uv run --locked --group audit pip-audit -r "$$req" ); code=$$?; \
	rm -f "$$req"; exit $$code

audit-secrets: tools
	@gitleaks_bin="$$(command -v gitleaks || printf '%s/gitleaks' "$(MONORI_TOOLS_BIN)")"; \
	if [ ! -x "$$gitleaks_bin" ]; then \
		echo "gitleaks was not installed at $$gitleaks_bin" >&2; \
		exit 1; \
	fi; \
	"$$gitleaks_bin" detect --no-banner --redact

test: t-front t-back t-e2e

t-workflow:
	uv run --locked pytest -q ci/tests/test_pr_workflow.py ci/tests/test_main_workflow.py

t-fast:
	cd web && npx vitest run --exclude "src/**/*.test.tsx"
	uv run --locked --group test pytest -q server/tests -m "not integration"
	$(MAKE) t-ci-unit

t-medium:
	cd web && npx vitest run --exclude "src/**/*.test.ts"
	uv run --locked --group test pytest -q server/tests -m integration
	$(MAKE) t-ci-integration

t-ci:
	$(MAKE) t-ci-unit
	$(MAKE) t-ci-integration

t-ci-unit:
	uv run --locked --group test pytest -q ci/tests --ignore=ci/tests/integration

t-ci-integration:
	COMPOSE="$(COMPOSE)" bash scripts/ci-tests.sh

t-slow: t-e2e

t-slow-ui: t-e2e-ui

t-front:
	cd web && npx vitest run

t-back:
	uv run --locked --group test pytest -q server/tests

t-e2e:
	COMPOSE="$(COMPOSE)" bash scripts/e2e.sh

t-e2e-ui:
	COMPOSE="$(COMPOSE)" bash scripts/e2e.sh --ui

coverage:
	COMPOSE="$(COMPOSE)" bash scripts/coverage-tree.sh

perf-front-diff:
	BASE="$(BASE)" COMPOSE="$(COMPOSE)" bash scripts/frontend-perf.sh

m-front:
	@set +e; \
	thr=$(MUTATION_THRESHOLD); \
	echo "── stryker: building the per-test coverage map; mutation progress begins after this phase ──"; \
	( cd web && MUTATION_THRESHOLD=$$thr ./node_modules/.bin/stryker run stryker.conf.ts ); web=$$?; \
	node scripts/stryker-summary.mjs; \
	echo "── frontend mutation gate (threshold $$thr%): stryker exit=$$web ──"; \
	exit $$web

# mutate a single file for a quick, isolated read: `make m-front-file FILE=src/pages/DashboardPage.tsx`
# a throwaway incremental cache keeps the run fresh and leaves the shared report untouched
m-front-file:
	@if [ -z "$(FILE)" ]; then \
		echo "usage: make m-front-file FILE=src/pages/DashboardPage.tsx"; exit 2; \
	fi
	cd web && ./node_modules/.bin/stryker run stryker.conf.ts --mutate "$(FILE)" --incrementalFile "$$(mktemp -u -t stryker-file.XXXXXX).json"

m-front-diff:
	@set +e; \
	git rev-parse --verify --quiet "$(BASE)" >/dev/null || { echo "mutation-diff: BASE='$(BASE)' is not a valid revision"; exit 1; }; \
	ranges=$$(git diff --diff-filter=ACMR --unified=0 "$(BASE)...HEAD" -- web/src | \
		awk '/^diff --git / { file=$$4; sub(/^b\/web\//, "", file); eligible=(file ~ /^src\/.*\.tsx?$$/ && file !~ /\.test\.tsx?$$/ && file != "src/main.tsx" && file !~ /^src\/test\// && file != "src/components/Meadow.tsx" && file != "src/components/GlyphFlower.tsx" && file !~ /^src\/demo\//); next } \
		/^@@ / { hunk=$$0; sub(/^.*\+/, "", hunk); sub(/ .*/, "", hunk); split(hunk, parts, ","); start=parts[1]; count=(parts[2] == "" ? 1 : parts[2]); if (eligible && count > 0) { end=start + count - 1; found[file] = found[file] (found[file] == "" ? "" : ",") file ":" start "-" end } } \
		END { for (file in found) printf "%s,", found[file] }' | sed 's/,$$//'); \
	if [ -z "$$ranges" ]; then \
		echo "mutation-diff: no changed frontend lines — pass"; exit 0; \
	fi; \
	( cd web && GITHUB_STEP_SUMMARY= MUTATION_THRESHOLD=0 ./node_modules/.bin/stryker run stryker.conf.ts --incremental --mutate "$$ranges" ); web=$$?; \
	node scripts/mutation-diff-gate.mjs "$(BASE)" web/reports/stryker-incremental.json "$(MUTATION_DIFF_THRESHOLD)"; gate=$$?; \
	if [ $$web -ne 0 ] || [ $$gate -ne 0 ]; then exit 1; fi

m-back:
	@set +e; \
	thr=$(MUTATION_THRESHOLD); \
	( mkdir -p mutants && uv run --locked --group mutation scripts/mutmut.sh run --max-children $(MUTATION_JOBS) 2>mutmut-stderr.log ); mutmut=$$?; \
	mv mutmut-stderr.log mutants/mutmut-stderr.log; \
	( mkdir -p mutants && uv run --locked --group mutation scripts/mutmut.sh export-cicd-stats ); export=$$?; \
	if [ $$export -eq 0 ]; then \
		uv run --locked --group mutation python -m monori.ci.lib.mutation_gate mutants/mutmut-cicd-stats.json $$thr; srv=$$?; \
	else \
		srv=$$export; \
	fi; \
	if [ -s mutants/mutmut-stderr.log ]; then echo "── mutmut diagnostics: mutants/mutmut-stderr.log ──"; fi; \
	echo "── Python mutation gate (threshold $$thr%, workers $(MUTATION_JOBS)): mutmut run exit=$$mutmut, mutmut gate exit=$$srv ──"; \
	if [ $$mutmut -ne 0 ] || [ $$srv -ne 0 ]; then exit 1; fi

mutation-python: m-back

m-back-diff:
	@set +e; \
	git rev-parse --verify --quiet "$(BASE)" >/dev/null || { echo "mutation-diff: BASE='$(BASE)' is not a valid revision"; exit 1; }; \
	if git diff --quiet "$(BASE)...HEAD" -- server/app ci/lib ci/quality_graph common; then \
		echo "mutation-diff: no changed Python files — pass"; exit 0; \
	fi; \
	paths=$$(git diff --diff-filter=ACMR --name-only "$(BASE)...HEAD" -- server/app ci/lib ci/quality_graph common '*.py' | sed -e 's#^server/#monori.server.#' -e 's#^ci/#monori.ci.#' -e 's#^common/#monori.common.#' -e 's#\.py$$##' -e 's#/#.#g' -e 's#$$#.*#' | paste -sd' ' -); \
	if [ -z "$$paths" ]; then \
		echo "mutation-diff: no changed Python source files — pass"; exit 0; \
	fi; \
	set -- $$paths; \
	baseline=$$(mktemp -d); trap 'rm -rf "$$baseline"' EXIT; \
	cold_start=0; if [ -d mutants ]; then cp -a mutants "$$baseline/mutants"; else mkdir -p "$$baseline/mutants"; cold_start=1; fi; \
	( mkdir -p mutants && uv run --locked --group mutation scripts/mutmut.sh run --max-children $(MUTATION_JOBS) "$$@" 2>mutmut-stderr.log ); mutmut=$$?; \
	mv mutmut-stderr.log mutants/mutmut-stderr.log; \
	args="--mutants mutants --baseline $$baseline/mutants --base $(BASE) --threshold $(MUTATION_DIFF_THRESHOLD)"; \
	if [ $$cold_start -eq 1 ]; then args="$$args --skip-new-survivors"; fi; \
	uv run --locked --group mutation python -m monori.ci.lib.mutation_diff_gate $$args; gate=$$?; \
	if [ -s mutants/mutmut-stderr.log ]; then echo "── mutmut diagnostics: mutants/mutmut-stderr.log ──"; fi; \
	echo "── Python diff mutation gate (threshold $(MUTATION_DIFF_THRESHOLD)%, workers $(MUTATION_JOBS)): mutmut run exit=$$mutmut, gate exit=$$gate ──"; \
	if [ $$mutmut -ne 0 ] || [ $$gate -ne 0 ]; then exit 1; fi

mutation-diff:
	@set +e; \
	$(MAKE) BASE="$(BASE)" MUTATION_DIFF_THRESHOLD=$(MUTATION_DIFF_THRESHOLD) m-front-diff; front=$$?; \
	$(MAKE) BASE="$(BASE)" MUTATION_DIFF_THRESHOLD=$(MUTATION_DIFF_THRESHOLD) m-back-diff; back=$$?; \
	echo "── diff mutation gates: frontend exit=$$front, Python exit=$$back ──"; \
	if [ $$front -ne 0 ] || [ $$back -ne 0 ]; then exit 1; fi

mutation:
	@set +e; \
	$(MAKE) MUTATION_THRESHOLD=$(MUTATION_THRESHOLD) m-front; front=$$?; \
	$(MAKE) MUTATION_THRESHOLD=$(MUTATION_THRESHOLD) m-back; back=$$?; \
	echo "── mutation gates: frontend exit=$$front, Python exit=$$back ──"; \
	if [ $$front -ne 0 ] || [ $$back -ne 0 ]; then exit 1; fi

check: fmt-check lint type analyze t-fast
