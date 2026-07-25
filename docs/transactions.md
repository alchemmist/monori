# Transactions

Transactions are the ledger monori budgets against. Each one is a signed amount
(negative is money out, positive is money in), a date, a description, and — once
categorized — a link to a category. A transaction lands in a budget month by its
date and in an envelope by its category.

Every amount is an integer in kopecks/cents, so nothing rounds.

## The Transactions page

The **Transactions** page lists the ledger newest-first, 100 rows per page. It
shows the date (`dd.mm.yyyy`), the description, the bank's own category label, the
signed amount, the account, the assigned category, and your own comment.

### Filters

- **Search** — matches the description, the bank category or your comment,
  case-insensitive.
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

### Editing a row

Date, description, amount and comment are edited in place: click the value, type
over it, and **Enter** (or **Tab**, or clicking away) saves. **Escape** leaves
the row as it was. The amount is typed in rubles and keeps its sign — a leading
minus is money out, no minus is money in — and is stored as kopecks, so nothing
rounds. Changing the date moves the row to where it belongs in the ledger.

The **Comment** column is yours: the bank never fills it. It is empty and quiet
until you point at a row, and everything typed there is searchable from the
search box above.

Every edit saves in the background and is reflected in the budget, the dashboard
and the balances immediately. If the server refuses the change, the row snaps
back to the value it had and a message says so, rather than leaving a total
quietly wrong until the next reload.

Rows that belong to a transfer, and hidden rows, are read-only: split the
transfer or unhide the row first.

### Deleting a row

The **…** menu at the end of a row deletes it, after a confirmation that spells
the row out. Deleting is final — the confirmation offers to hide the row
instead, which keeps it out of every total but leaves it recoverable from the
**Hidden** toggle.

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

The page above covers a single row end to end: add, edit every field, comment,
hide, delete. What is not there yet is working on many rows at once — bulk
categorize, move and delete exist in the [REST API](api.md#transactions) and an
advanced search-and-bulk-edit explorer is tracked in issue #17. Until it ships,
a mass change is a call away through the API.
