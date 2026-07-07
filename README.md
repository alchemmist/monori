# monori

Self-hosted, single-user **envelope budgeting** — the YNAB-style workflow of a
spreadsheet budget, rebuilt as a fast web app. Born as a migration of a personal
Google Sheets budget, it keeps the sheet's exact math while adding inline
editing, statement import with auto-categorization, a full-year grid and a
dashboard with analytics.

All money is stored as integer kopecks/cents end to end — no floating-point
rounding anywhere.

## Features

- **Envelope budgeting** with carryover: positive leftovers roll over, overspend
  doesn't; "Available to Budget" and overspent recompute on every keystroke.
- **Month view** for envelope work and a **full-year grid** — all 12 months at
  once as a frozen-pane spreadsheet (Budgeted / Activity / Balance per category),
  with group subtotals and an income/budgeted/available summary band.
- **Statement import**: paste bank rows → preview shows new / duplicate /
  auto-categorized (keyword rules + hash-based dedup) → commit.
- **Dashboard**: rolling KPIs, income vs expenses trend with a time navigator,
  and a yearly analytics section — plan vs fact, a budget-discipline heatmap,
  year-over-year, weekday / day-of-month profiles, top merchants.
- Light/dark, responsive down to mobile.

## Stack

- **web/** — React (plain JS) + Vite + [Gravity UI](https://gravity-ui.com) +
  zustand. The budget engine (`web/src/engine/budget.js`) runs fully
  client-side; every edit recomputes carryover chains in the same frame.
- **server/** — FastAPI + SQLite. Thin persistence + import: statement parsing,
  keyword auto-categorization, hash-based dedup.
- **deploy/** — multi-stage Dockerfile (web build + python runtime) and compose.

## Quick start (Docker)

```sh
cd deploy
docker compose -f docker-compose.example.yml up -d --build
# open http://localhost:8000
```

Data lives in a mounted `deploy/data/monori.db`. The app starts with an empty
database (schema is created automatically); add category groups and categories
from the Budget page, then import a statement.

> **Security note.** monori is single-user and has **no built-in
> authentication** — anyone who can reach the port can read and edit the budget.
> Do not expose it directly to the internet. Put it behind a reverse proxy that
> terminates TLS and adds auth (e.g. Caddy/nginx with basic auth or an SSO
> proxy), or keep it on a private network / VPN.

## Local development

```sh
make dev     # uvicorn (:8077, --reload) + vite (:5173, proxies /api) together
```

Also `make api`, `make web`, `make test`, `make build`. Requires
[uv](https://docs.astral.sh/uv/) for the server and Node 22+ for the web app.
There is also `deploy/docker-compose.dev.yml` to run the dev stack in containers.

## Budget semantics

- `balance(cat, m) = max(balance(cat, m-1), 0) + budgeted + outflows` — positive
  leftovers roll over, overspending does not.
- `available(m) = available(m-1) + overspent(m-1) + income(m) - budgetedTotal(m)`.
- "To be Budgeted" counts as real inflow; internal transfers are left
  uncategorized and excluded from analytics automatically.

## Importing a statement

Transactions → **Import statement** → paste bank rows (tab/semicolon-separated,
as copied from a bank export) → the preview marks new / duplicate /
auto-categorized rows → **Import**. Categorization uses per-category keyword
rules you can edit; dedup is by `sha1(date|amount|description)`.

## Migrating from a Google Sheets budget

`migration/` turns a copy of the monori budget spreadsheet template into
monori's JSON datasets and a golden reference used by the engine tests. It
targets that specific sheet layout (Transactions, Categories, one sheet per
year). To migrate your own copy:

```sh
export MONORI_SHEET_ID=<spreadsheet id from its URL>
export MONORI_GSHEETS_TOKEN=~/.config/monori/gsheets-token.json  # google oauth token
python migration/export_sheets.py     # dump sheets -> migration/raw/
python migration/build_reference.py   # normalize -> migration/out/
```

## Tests

- `cd web && npx vitest run` — engine **golden tests** reproduce every
  budgeted/outflows/balance/available figure of the reference spreadsheet over
  2020–2027; `analytics.test.js` covers the analytics helpers.
- `cd server && uv run pytest` — statement parser, categorizer, and API.

## Ops notes

- Data is a single SQLite file at `MONORI_DB` (default `server/data/monori.db`,
  or `/app/data/monori.db` in the container). Back it up with a consistent
  SQLite copy (`sqlite3 monori.db ".backup ..."`) on a cron.
- The container serves the built web app and the API from one process on port
  8000.




