# Configuration

monori is configured entirely through environment variables. There is no config
file.

## Environment variables

| Variable | Default | Purpose |
| ---------- | --------- | --------- |
| `MONORI_DB` | `server/data/monori.db` | Absolute path to the SQLite database file. Its parent directory is created on startup. In Docker this is set to `/app/data/monori.db`. |
| `MONORI_API_TOKEN` | *(unset)* | Optional bearer token. When set, every `/api` data route (and `/api/snapshot`) requires `Authorization: Bearer <token>`; the docs site and OpenAPI endpoints (`/docs`, `/api-docs`, `/api-redoc`, `/openapi.json`) stay public. When unset, the API is open. |
| `API_PORT` | `8077` | Dev only — the port the local API runs on and the web dev server proxies to. Set via the `make` variable of the same name. |

The production container also sets `MONORI_DB=/app/data/monori.db` in the
`Dockerfile` itself, and the server auto-detects its bundled frontend at
`server/static` (populated by `make build` or the Docker build).

## The database file

- It is a single SQLite file. Everything — groups, categories, transactions,
  budgets — lives in it. Back it up by copying the file.
- SQLite runs in **WAL mode** with foreign keys enabled. Alongside `monori.db`
  you may see `monori.db-wal` and `monori.db-shm`; those are normal and belong to
  the same database.
- It is a single-user, single-writer store. Do not point two running instances
  at the same file.

To move a budget between machines, stop the app and copy `monori.db` (and, to be
safe, the `-wal` file if present).

## API authentication

Setting `MONORI_API_TOKEN` turns on a constant-time bearer-token check on every
`/api` data route, including `GET /api/snapshot`. Requests without a matching
`Authorization: Bearer <token>` header get `401`. The docs site (`/docs`) and the
OpenAPI endpoints (`/api-docs`, `/api-redoc`, `/openapi.json`) are intentionally
left public so the documentation is always reachable.

```bash
docker run -e MONORI_API_TOKEN=$(openssl rand -hex 32) ...
```

The frontend is served from the same origin as the API, so it does not need the
token for same-origin browsing when the token is unset. If you enable the token,
the browser app expects to reach the API through a proxy that injects the header,
or with the token left unset behind a network boundary that provides auth
instead. See [the API reference](api.md#authentication) for details.
