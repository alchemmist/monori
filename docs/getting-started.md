# Getting started

There are two ways to run monori: a Docker deployment for everyday use, and a
local dev setup with hot-reload for hacking on the code.

## Deploy with Docker

The production image is a single container: a multi-stage build compiles the web
app, then a Python image serves both the API and the compiled frontend on one
port (8000). The SQLite database lives on a mounted volume so it survives
restarts and rebuilds.

Use `deploy/docker-compose.example.yml` as a starting point:

```yaml
services:
  monori:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    container_name: monori
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      MONORI_DB: /app/data/monori.db
```

Then:

```bash
cd deploy
docker compose -f docker-compose.example.yml up --build -d
```

Open <http://localhost:8000>. The database is created on first run at
`./data/monori.db` on the host.

> **Security.** monori has no built-in HTTPS and only an optional bearer token
> on the API (see [Configuration](configuration.md)). Put it behind a reverse
> proxy that terminates TLS and adds authentication before exposing it beyond
> localhost. Migrating to a proper in-app login is tracked in issue #34.

## Run locally for development

Requirements: [`uv`](https://docs.astral.sh/uv/) for the Python side and Node 22
for the web side.

The whole dev loop is driven by `make`. To bring up both services with
hot-reload in containers:

```bash
make up      # docker compose dev stack: web on 5173, api on 8077
make down    # stop it
```

Or run the two halves directly on the host:

```bash
make api     # uvicorn --reload on :8077
make web     # vite dev server on :5173, proxying the API
```

The web dev server proxies API calls to `API_PORT` (default `8077`), so both
must be up together. Open <http://localhost:5173>.

## Build the production bundle by hand

```bash
make build   # vite build, then copy web/dist into server/static
```

FastAPI serves `server/static` as the SPA when that directory exists, so after a
build you can run just `make api` and hit the full app on the API port.

## First run

The app starts empty. To get going:

1. Create category **groups** (income and expense) and **categories** inside them.
2. Add transactions manually, or paste a bank statement via **Import** on the
   Transactions page.
3. Give categories **keywords** so future imports auto-categorize themselves.
4. Fill in the **budget grid** for the current month.

See [Budgeting](budgeting.md) and [Importing statements](importing.md) for the
details.
