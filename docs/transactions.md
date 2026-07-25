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

### Loading

The app opens on the newest slice of the ledger and pulls the rest in the
background, so first paint doesn't wait on years of history. While that runs, a
small progress ring sits next to the row count and disappears once the last
chunk lands; older rows and every total that depends on them (budgets, the
dashboard) fill in as they arrive. With **reduce motion** turned on, the ring is
replaced by a plain percentage.

### Categorizing

Each row has an inline category dropdown — pick a category to assign or reassign
the transaction. This is the main day-to-day task after an import: sweep the
uncategorized rows into envelopes so the budget reflects reality. The account
column has a matching dropdown to move a row to a different account.

### Adding a transaction by hand

The **Add transaction** button opens a side tab: pick expense or income, type
the amount in rubles (`123.45` or `123,45` — it is stored as kopecks), and add a
description, date, account, category and comment. **Add** records the row
straight into the ledger and the tab stays open, cleared for the next one, so a
whole run of cash spends goes in without reopening anything. Amount, description
and comment reset after each row; the date, account and category stay put,
because a run of entries is usually from the same day, card and envelope. Enter
records the row from any field.

The tab is docked, not modal: the ledger behind it stays readable and clickable,
the tab collapses to a strip, and it survives navigating to another page.

Manual rows are ordinary transactions with `source` set to `manual` — the
budget, the dashboard and the year grid count them exactly like imported ones.

### Transfers

A transfer between two of your own accounts is shown as **one row**, set apart
from the ledger around it, reading `source account → destination account` with
the amount untinted — a transfer nets to zero, so neither red nor green would be
telling the truth. The two transactions behind it are still there: the chevron
on the row opens them up underneath.

The **Transfer** button records one by hand. **Find transfers** scans the ledger
for pairs the bank delivered as two rows and offers to merge them; monori also
does this by itself after every import and sync. The row menu splits a transfer
back into two ordinary transactions, or deletes both.

Transfers are uncategorized on purpose, so they never show up as income or
expense in the budget or on the dashboard. See [Accounts](accounts.md).

### Importing

The **Import statement** button opens the import dialog. See
[Importing statements](importing.md) for the format and the two-step
preview → commit flow.

## Where transactions come from

- **Import** — rows created by pasting a bank statement. Their `source` is
  `import`, and they are deduplicated by a content hash so re-importing an
  overlapping statement does not double them.
- **Manual** — rows entered by hand, through the **Add transaction** tab or the
  API, with `source` set to `manual`.

## Editing beyond the page

The full CRUD surface for transactions — create, edit every field, delete, and
bulk operations (bulk categorize/move/delete) — exists in the
[REST API](api.md#transactions). In the app, adding and categorizing are
covered by the page above; inline editing of every field, deleting a row and the
comment column are tracked in issue #16, and an advanced search-and-bulk-edit
explorer in issue #17. Until those ship, anything more is a call away through the
API.
