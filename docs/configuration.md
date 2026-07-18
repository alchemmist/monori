# Configuration

monori is configured entirely through environment variables. There is no config
file.

## Environment variables

| Variable | Default | Purpose |
| ---------- | --------- | --------- |
| `MONORI_DB` | `server/data/monori.db` | Absolute path to the SQLite database file. Its parent directory is created on startup. In Docker this is set to `/app/data/monori.db`. |
| `MONORI_API_TOKEN` | *(unset)* | Optional bearer token. When set, every `/api` data route (and `/api/snapshot`) requires `Authorization: Bearer <token>`; the docs site and OpenAPI endpoints (`/docs`, `/api-docs`, `/api-redoc`, `/openapi.json`) stay public. When unset, the API is open. |
| `MONORI_ENCRYPTION_KEY` | *(unset)* | Required only for **bank sync connectors** (see below). A urlsafe base64 32-byte Fernet key used to encrypt stored bank credentials and cached sessions at rest. When unset, connections cannot be created and the feature is disabled. Generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
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

## Bank sync connectors

Beyond the manual statement paste, an account can be connected to a **bank
connector** that pulls transactions on demand ("Sync now" on the Accounts page).
There is no background scheduler — syncs run only when you trigger them. Fetched
rows go through the exact same pipeline as manual import (hash-based dedup +
keyword categorization), so re-syncing never double-counts.

Enabling connectors takes two things:

1. **An encryption key.** Set `MONORI_ENCRYPTION_KEY` (see the table above). Bank
   credentials and the cached session are stored encrypted at rest with it; a
   connection can never be created without it.
2. **The connector's runtime.** The bundled T-Bank connector drives the real web
   cabinet with a headless browser, so it needs the optional `connectors` extra
   and a browser:

   ```bash
   pip install 'monori-server[connectors]'
   playwright install chromium
   ```

The T-Bank connector logs in **as you** (phone, then the SMS code the bank sends)
to download your operations export. To avoid an SMS on every sync it keeps the
authenticated **browser session** (cookies, trusted-device identity) and, from
the bank's "create a code" screen, a quick-login code — both stored **encrypted**
in the connection with the same key. So only the first sync needs an SMS; later
syncs restore the session, falling back to the code when it expires. During a
sync the profile is unpacked into an owner-only temporary directory and removed
right after, so the reusable banking state never sits in plaintext on disk.

This is automated access to your own account and is a grey area under the bank's
terms of service — use it on your own account at your own risk. Because it holds
real access to financial data, keep the instance off the open internet and set
`MONORI_API_TOKEN`. Set `MONORI_CONNECTOR_DEBUG=1` to dump a screenshot + HTML at
each login step (into the database directory) when tuning it.

The connector interface is pluggable — additional banks/mechanisms register
themselves the same way, one at a time.
