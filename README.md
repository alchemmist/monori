# monori

monori is a self-hosted, single-user **envelope budgeting** app — the YNAB-style workflow of a spreadsheet budget, rebuilt as a fast web app. It keeps the exact math of the Google Sheets budget it grew from, and adds inline editing, bank-statement import with auto-categorization, a full-year budget grid, and a dashboard with analytics. All money is stored as integer kopecks/cents end to end, so there is no floating-point rounding anywhere.

![monori dashboard](docs/screenshot.png)

## Documentation

Full docs live in [`docs/`](docs/README.md):

- [Getting started](docs/getting-started.md) — run locally or deploy with Docker.
- [Configuration](docs/configuration.md) — environment variables and the database.
- [Budgeting](docs/budgeting.md) — the envelope model and the budget grid.
- [Transactions](docs/transactions.md) and [Importing statements](docs/importing.md).
- [Dashboard & analytics](docs/dashboard-analytics.md).
- [REST API](docs/api.md) and [Data model](docs/data-model.md).
- [Development](docs/development.md) — the stack, the `make` targets, testing.

## License

[MIT](LICENSE) © alchemmist
