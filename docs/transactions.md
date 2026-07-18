# Transactions

Transactions are the ledger monori budgets against. Each one is a signed amount
(negative is money out, positive is money in), a date, a description, and — once
categorized — a link to a category. A transaction lands in a budget month by its
date and in an envelope by its category.

Every amount is an integer in kopecks/cents, so nothing rounds.

## The Transactions page

The **Transactions** page lists the ledger newest-first, 100 rows per page. It
shows the date (`dd.mm.yyyy`), the description, the bank's own category label, the
signed amount, the account, and the assigned category.

### Filters

- **Search** — matches the description or the bank category, case-insensitive.
- **Category** — a specific category, or *uncategorized* to find rows that still
  need a home.
- **Account** — narrow to one account (shown once you have more than one).
- **Year** — narrow to a single year.

Filtering happens live over the loaded snapshot; changing a filter resets you to
the first page.

### Categorizing

Each row has an inline category dropdown — pick a category to assign or reassign
the transaction. This is the main day-to-day task after an import: sweep the
uncategorized rows into envelopes so the budget reflects reality. The account
column has a matching dropdown to move a row to a different account.

### Transfers

The **Transfer** button moves money between two of your own accounts. It records
two linked rows — money out of one account, the same amount into the other —
tagged with a **transfer** badge. Transfers are uncategorized on purpose, so they
never show up as income or expense in the budget or on the dashboard. See
[Accounts](accounts.md).

### Importing

The **Import statement** button opens the import dialog. See
[Importing statements](importing.md) for the format and the two-step
preview → commit flow.

## Where transactions come from

- **Import** — rows created by pasting a bank statement. Their `source` is
  `import`, and they are deduplicated by a content hash so re-importing an
  overlapping statement does not double them.
- **Manual** — rows created through the API with `source` set to `manual`.

## Manual editing via the API

The full CRUD surface for transactions — create, edit every field, delete, and
bulk operations (bulk categorize/move/delete) — already exists in the
[REST API](api.md#transactions). A dedicated in-app editing UI for it (add a row,
edit any field, restore the comment column) is tracked in issue #16, and an
advanced search-and-bulk-edit explorer in issue #17. Until those ship, the page
above covers viewing, filtering, and per-row categorization; anything more is a
call away through the API.
