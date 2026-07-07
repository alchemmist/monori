API_PORT ?= 8077
COMPOSE ?= $(shell command -v docker >/dev/null 2>&1 && echo "docker compose" || echo "podman compose")

.PHONY: dev down api web test build

## dev: full stack in containers with hot reload (web on :5173, api on :8077)
dev:
	$(COMPOSE) -f deploy/docker-compose.dev.yml up

down:
	$(COMPOSE) -f deploy/docker-compose.dev.yml down

## api / web: run natively without containers
api:
	cd server && uv run uvicorn app.main:app --port $(API_PORT) --reload

web:
	cd web && API_PORT=$(API_PORT) npm run dev

test:
	cd web && npx vitest run
	cd server && uv run pytest

build:
	cd web && npm run build
	rm -rf server/static
	cp -r web/dist server/static
