# Data model

Everything monori knows lives in one SQLite file (`MONORI_DB`, default
`server/data/monori.db`). The schema is created on first connection and runs in
WAL mode with foreign keys enabled. Five tables hold the whole budget.

Schema changes to existing databases are applied by small ordered migrations
tracked with SQLite's `PRAGMA user_version`; connecting to an older database
upgrades it in place (see the accounts migration below).

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

### `accounts`

Where money physically sits: bank cards, cash, savings. Every transaction
belongs to exactly one account.

| Column | Type | Notes |
| -------- | ------ | ------- |
| `id` | INTEGER PK | |
| `name` | TEXT | unique |
| `type` | TEXT | `card` / `cash` / `savings` / `other`; default `other` |
| `currency` | TEXT | ISO code, default `RUB`. A label only — monori is single-currency for now (see issue #29) |
| `sort` | INTEGER | display order; default `0` |
| `archived` | INTEGER | `0`/`1`; default `0` |
| `opening_balance` | INTEGER | kopecks; default `0` |
| `opening_date` | TEXT | ISO date, nullable |

An account's **running balance** is `opening_balance` plus the sum of its
transactions. Reconcile compares this to your real bank balance and posts an
adjustment for any difference.

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
| `account_id` | INTEGER | → `accounts(id)`, NOT NULL |
| `transfer_id` | TEXT | links the two legs of a transfer; `NULL` for normal rows |
| `comment` | TEXT | default `''` |
| `hash` | TEXT | `sha1(date \| amount \| description)`, for dedup |
| `source` | TEXT | `import` / `manual` / `transfer` / `adjustment` / `sheets`; default `import` |

Indexes: `date`, `hash`, `category_id`, `account_id`.

A **transfer** between your own accounts is two linked rows sharing a
`transfer_id`: a negative leg on the source account and a positive leg on the
destination. Both are uncategorized, so a transfer never counts as income or
expense in analytics — this is enforced by construction, not by convention.

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
- Deleting an **account** reassigns its transactions to another account
  (`?reassignTo=`). Since every transaction must belong to an account, deleting a
  non-empty account without a target is refused, and the last remaining account
  cannot be deleted.
- These rules mean a delete never silently loses transactions — they are kept,
  just uncategorized or moved.

## Accounts migration

Databases created before accounts existed are upgraded on first connection: a
default **T-Bank** account is created and every existing transaction is
backfilled onto it, so current data behaves exactly as before. The migration
rebuilds the `transactions` table to add the NOT NULL `account_id`, then records
itself via `PRAGMA user_version` so it runs only once.

## Dedup hashing

The `hash` is `sha1(f"{date}|{amount}|{description}")`. Two transactions are
"the same" only when date, amount, and description all match. Import uses this to
avoid inserting a row that already exists; see [Importing](importing.md).

## Backups

The database is a single file. To back up, copy `monori.db` (and its `-wal`
sidecar if present) while the app is stopped, or use SQLite's own online backup.
A backup/restore UI is planned in issue #28.
