# monori documentation

monori is a self-hosted, single-user **envelope budgeting** app — the YNAB-style
workflow of a spreadsheet budget, rebuilt as a fast web app. It keeps the exact
math of the Google Sheets budget it grew from, and adds inline editing,
bank-statement import with auto-categorization, a full-year budget grid, and a
dashboard with analytics. All money is stored as integer kopecks/cents end to
end, so there is no floating-point rounding anywhere.

## Contents

- [Getting started](getting-started.md) — run it locally or deploy with Docker.
- [Configuration](configuration.md) — environment variables and the database file.
- [Budgeting](budgeting.md) — the envelope model, how the math works, using the grid.
- [Transactions](transactions.md) — the ledger, filters, categorization, manual edits.
- [Accounts & transfers](accounts.md) — multiple accounts, transfers, reconcile.
- [Importing statements](importing.md) — the statement format, auto-categorization, dedup.
- [Migrating from a spreadsheet](migration.md) — one-shot import of a YNAB-style workbook.
- [Dashboard & analytics](dashboard-analytics.md) — charts and the annual report.
- [REST API](api.md) — every endpoint, request and response shapes, auth.
- [Data model](data-model.md) — the SQLite schema and the money representation.
- [Development](development.md) — the tech stack, the `make` targets, testing.

## At a glance

- **Frontend** — React 19 + Vite, built on [Gravity UI](https://gravity-ui.com/).
- **Backend** — FastAPI on Python 3.12, single-file SQLite database.
- **State** — the whole state is served in one `GET /api/snapshot`; the budgeting
  math runs client-side as pure functions.
- **Single user** — there is no multi-tenancy; one deployment holds one budget.

## Roadmap

The sidebar shows planned destinations as disabled entries, each tied to a
tracking issue: Accounts (#2), Net worth (#19), Goals (#15), Debts & loans (#20),
Reports (#18), Import history (#22), Rules (#21).
