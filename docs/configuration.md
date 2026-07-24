# Configuration

monori is configured entirely through environment variables. There is no config
file.

## Environment variables

| Variable | Default | Purpose |
| ---------- | --------- | --------- |
| `MONORI_DB` | `server/data/monori.db` | Absolute path to the SQLite database file. Its parent directory is created on startup. In Docker this is set to `/app/data/monori.db`. |
| `MONORI_ENCRYPTION_KEY` | *(auto)* | A urlsafe base64 32-byte Fernet key used to encrypt stored bank credentials and cached sessions at rest. If unset, one is generated once and persisted owner-only as `.encryption_key` next to the database. Set it explicitly to manage the key yourself: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `MONORI_AUTH_SECRET` | *(auto)* | Secret used to sign in-app auth JWTs (issue #34). If unset, a random one is generated once and persisted owner-only as `.auth_secret` next to the database, so logins survive restarts. Set it explicitly to share a secret across replicas or rotate it (rotating invalidates existing tokens). |
| `MONORI_ADMIN_EMAILS` | *(unset)* | Comma-separated emails that get admin rights (the in-app Admin panel: instance analytics and user management). The flag is synced on every login, so this variable is the single source of truth — remove an email and the rights are revoked at the next login. |
| `MONORI_SYNC_URL` | *(unset)* | Base URL of the standalone bank-sync service (e.g. `http://sync:8010` in the production compose). When set, the API delegates bank syncs there over the private network; when unset, syncs run in-process, which requires the `connectors` extra and a Playwright Chromium in the API image. |
| `API_PORT` | `8077` | Dev only — the port the local API runs on and the web dev server proxies to. Set via the `make` variable of the same name. |

The production back container sets `MONORI_DB=/app/data/monori.db` in
`deploy/Dockerfile.back`; in production the static frontend is served by the
front (nginx) container. Outside Docker the server also auto-detects a bundled
frontend at `server/static` (populated by `make build`).

## The database file

- It is a single SQLite file. Everything — groups, categories, transactions,
  budgets — lives in it. Back it up by copying the file.
- SQLite runs in **WAL mode** with foreign keys enabled. Alongside `monori.db`
  you may see `monori.db-wal` and `monori.db-shm`; those are normal and belong to
  the same database.
- It is a single-writer store holding all registered users. Do not point two
  running instances at the same file.

To move a budget between machines, stop the app and copy `monori.db` (and, to be
safe, the `-wal` file if present).

## API authentication

monori is multi-user: people register and sign in in the app, and every `/api`
data route requires the resulting bearer JWT. Each user sees only their own
data. The docs site (`/docs`) and the OpenAPI endpoints (`/api-docs`,
`/api-redoc`, `/openapi.json`) are intentionally left public so the
documentation is always reachable. The former instance-wide `MONORI_API_TOKEN`
guard is retired. See [the API reference](api.md#authentication) for the auth
endpoints and scoping rules.

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
