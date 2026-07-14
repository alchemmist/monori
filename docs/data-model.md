# Data model

Everything monori knows lives in one SQLite file (`MONORI_DB`, default
`server/data/monori.db`). The schema is created on first connection and runs in
WAL mode with foreign keys enabled. Four tables hold the whole budget.

## Money

Every amount — transactions, budgets — is a **signed integer in kopecks/cents**.
A ruble value like `1 500,00` is stored as `150000`. Expenses are negative,
income positive. There is no floating-point money anywhere; rubles exist only at
the display edge. This is what lets budget totals reconcile exactly with the
ledger.

## Tables

### `category_groups`

Top-level buckets that give categories their income/expense meaning.

| Column | Type | Notes |
| -------- | ------ | ------- |
| `id` | INTEGER PK | |
| `name` | TEXT | unique |
| `sort` | INTEGER | display order |
| `kind` | TEXT | `income` or `expense` (checked) |

### `categories`

The envelopes.

| Column | Type | Notes |
| -------- | ------ | ------- |
| `id` | INTEGER PK | |
| `group_id` | INTEGER | → `category_groups(id)` |
| `name` | TEXT | unique |
| `keywords` | TEXT | pipe-separated, for import auto-categorization; default `''` |
| `sort` | INTEGER | display order; default `0` |
| `archived` | INTEGER | `0`/`1`; default `0` |

### `transactions`

The ledger.

| Column | Type | Notes |
| -------- | ------ | ------- |
| `id` | INTEGER PK | |
| `date` | TEXT | ISO-8601 datetime |
| `amount` | INTEGER | signed kopecks; negative = expense |
| `description` | TEXT | default `''` |
| `bank_category` | TEXT | the bank's own label; default `''` |
| `mcc` | TEXT | merchant category code; default `''` |
| `category_id` | INTEGER | → `categories(id)`, `ON DELETE SET NULL` |
| `comment` | TEXT | default `''` |
| `hash` | TEXT | `sha1(date \| amount \| description)`, for dedup |
| `source` | TEXT | `import` or `manual`; default `import` |

Indexes: `date`, `hash`, `category_id`.

### `budgets`

One assigned amount per category per month.

| Column | Type | Notes |
| -------- | ------ | ------- |
| `category_id` | INTEGER | → `categories(id)`, `ON DELETE CASCADE` |
| `year` | INTEGER | |
| `month` | INTEGER | 1–12 (checked) |
| `amount` | INTEGER | kopecks |

Primary key is `(category_id, year, month)`, so there is at most one cell per
category-month. A cell with amount `0` is deleted rather than stored.

## Referential behavior

- Deleting a **category** sets `category_id` to `NULL` on its transactions (they
  become uncategorized) and cascade-deletes its budgets. The API also lets you
  reassign transactions to another category first (`?reassignTo=`).
- Deleting a **group** is refused while it still has categories.
- These rules mean a delete never silently loses transactions — they are kept,
  just uncategorized or moved.

## Dedup hashing

The `hash` is `sha1(f"{date}|{amount}|{description}")`. Two transactions are
"the same" only when date, amount, and description all match. Import uses this to
avoid inserting a row that already exists; see [Importing](importing.md).

## Backups

The database is a single file. To back up, copy `monori.db` (and its `-wal`
sidecar if present) while the app is stopped, or use SQLite's own online backup.
A backup/restore UI is planned in issue #28.
