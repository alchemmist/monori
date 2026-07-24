# Migrating from a spreadsheet

If you have been budgeting in a YNAB-style spreadsheet — the kind monori's own
Excel export produces — you can move your whole history into monori in one go:
category groups, categories with their keywords, every transaction, and the
budget grid for every year. No retyping.

The importer and the exporter share one format definition, so a monori export
re-imports cleanly: **export → import is a lossless round-trip** for groups,
categories, transactions and budgets.

## Running a migration

1. Download your workbook as `.xlsx` (in Google Sheets: *File → Download →
   Microsoft Excel*).
2. Open **Settings → Migrate from spreadsheet** and pick the file.
3. Review the preview: how many groups, categories, transactions and budget
   cells were found, plus any warnings and unparseable rows.
4. **Map accounts.** The workbook only knows card markers (like `*2947`) or
   account names; monori asks which of your accounts each marker should land
   on. Create the accounts first if they don't exist yet.
5. Pick a **budget policy** for cells that already have a value in monori:
   *Overwrite* takes the workbook's number, *Keep mine* leaves yours untouched.
6. Import. The result screen shows exactly what was created and what was
   skipped as a duplicate.

## The workbook format

The importer expects the structure monori's export writes:

- **`Categories`** — a table of `Sort Order`, `Category Group`, `Category`,
  `Keywords`. Group names carry a direction glyph: `▲` marks an income group,
  `▼` an expense group. A second table lists the groups themselves with their
  sort order and `IN`/`OUT` type. Keywords (pipe-separated, like
  `lenta|okey`) come along and immediately power auto-categorization.
- **`Transactions`** — bank-statement-shaped columns: operation datetime,
  status, signed amount, bank category, MCC, description. Optional monori
  columns (`Monori Category`, `Account`, `Comment`) are used when present —
  an explicit `Monori Category` wins over keyword matching.
- **Year sheets** (`2024`, `2025`, …) — the budget grid: categories down the
  side, `Budgeted / Outflows / Balance` per month. Only the *Budgeted* numbers
  are imported; outflows and balances are derived values that monori
  recomputes from your transactions.
- **`DashData`** — derived analytics; ignored on import for the same reason.

Unknown sheets and unrecognized rows are skipped with a warning, never a
silent drop.

## What the importer guarantees

- **Idempotent.** Every transaction is hashed (`date|amount|description`), and
  rows whose hash already exists on the target account are skipped. Running the
  same migration twice imports nothing the second time.
- **Merges by name.** A group or category that already exists in monori (same
  name, same group) is reused, not duplicated. Existing categories keep their
  keywords.
- **Batched.** Each migration lands as an import batch per account, so it shows
  up in the import history and can be rolled back as a unit.
- **Non-OK rows are skipped** (declined or held operations) and reported in
  the preview count.

## Limits

- Amounts are treated as rubles (kopeck precision); multi-currency workbooks
  are not yet understood.
- Transfers between accounts arrive as two ordinary transactions — link them
  in monori afterwards if you want them netted out of analytics.
