# monori

Personal envelope-budgeting app, migrated from the Google Sheets budget
(2020–2027). Lives at https://cash.alchemmist.xyz behind HTTPS + basic auth.

## Stack

- **web/** — React (plain JS) + Vite + Gravity UI + zustand. The budget engine
  (`web/src/engine/budget.js`) runs fully client-side: every budget edit
  recomputes carryover chains, overspent and Available to Budget in the same
  frame.
- **server/** — FastAPI + SQLite. Thin persistence + import: statement parsing,
  keyword auto-categorization (faithful port of the sheet's FIND_CATEGORIES),
  hash-based dedup. All money is integer kopecks end to end.
- **deploy/** — Dockerfile (multi-stage web build + python runtime), compose,
  runs on laba as container `monori` in the `personal-site_default` network,
  proxied by the shared Caddy with basic_auth.

## Budget semantics (same as the sheet)

- `balance(cat, m) = max(balance(cat, m-1), 0) + budgeted + outflows` — positive
  leftovers roll over, overspending does not.
- `available(m) = available(m-1) + overspent(m-1) + income(m) - budgetedTotal(m)`.
- "To be Budgeted" counts as real inflow; internal transfers are uncategorized
  and excluded from analytics automatically.

## Daily use

- **Import**: Transactions → Import statement → paste bank rows (same format as
  pasted into the sheet) → preview shows new/duplicate/auto-categorized → Import.
- **Budgeting**: Budget page, click any Budgeted cell, type, Enter. Month view
  for envelope work; Year view (`web/src/components/YearGrid.jsx`) shows all 12
  months at once as a frozen-pane spreadsheet — Budgeted / Activity / Balance
  per category per month, group subtotals, income/budgeted/available summary
  rows, like the original sheet. Density toggle: Full / Plan (budgets only) /
  Actual. Editing any cell recomputes the whole grid in the same frame.
- **Categories**: add/edit/delete from the group headers and row menus.
  Deleting a category asks where to move its transactions and never shifts
  anything else — this was the whole point of leaving Sheets.
- **Dashboard**: rolling KPIs, income/expenses trend with a time navigator, and
  a "Yearly analytics" section (`web/src/engine/analytics.js`) — plan vs fact, a
  budget-discipline heatmap (spent/budgeted per envelope per month), expenses
  year-over-year, weekday and day-of-month spending profiles, top merchants and
  per-year totals. Pick a year in the section header; everything follows.

## Tests

- `cd web && npx vitest run` — engine golden tests: reproduces every
  budgeted/outflows/balance/available figure of the original sheet over
  2020–2027 (one documented 30 RUB legacy artifact, see budget.golden.test.js).
  `analytics.test.js` covers the analytics helpers (yearly totals, merchant
  grouping, weekday profile, budget-discipline classification).
- `cd server && uv run pytest` — parser, categorizer (validated against 6718
  historical rows), API.

## Ops

- Data: `/home/www/monori/deploy/data/monori.db` (volume-mounted).
- Backup: `/home/www/monori/deploy/backup.sh` — consistent SQLite backup,
  gzip, keeps 14. Intended cron: `20 3 * * *`. Restore = gunzip + point
  `MONORI_DB` at the file (verified working).
- Redeploy: `git archive --format=tar HEAD | ssh laba 'tar -x -C /home/www/monori'`
  then `ssh laba 'cd /home/www/monori/deploy && docker compose up -d --build'`.
- Local dev: `make dev` — uvicorn (8077, --reload) + vite (5173, proxies
  `/api`) together. Also `make api` / `make web` / `make test` / `make build`.

## Migration provenance

`migration/` holds the Sheets export + golden reference builder. The original
spreadsheet is untouched and remains the archive/fallback. Parity was verified
three ways: DB vs sheet (6240 figures), JS engine vs sheet (all years), prod
snapshot vs local (checksums).
