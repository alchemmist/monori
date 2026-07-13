# Importing statements

Instead of typing transactions in by hand, you paste a bank statement export and
monori parses it, auto-categorizes each row from your keywords, drops duplicates,
and lets you review everything before it touches the database.

## The statement format

The importer reads the bank's own statement export — one transaction per line:

- **Delimiter** — tab or semicolon (auto-detected per line; tab wins if present).
- **Dates** — `dd.mm.yyyy`, optionally with a time: `dd.mm.yyyy hh:mm[:ss]`.
- **Amounts** — decimal commas, thousands spaces: `-1 500,00` becomes `-150000`
  kopecks. A leading `-` marks an outflow.
- **Columns** — at least 12, in this order:

  | # | Column | Used for |
  | --- | -------- | ---------- |
  | 1 | operation date | the transaction date |
  | 2 | payment date | — |
  | 3 | card | — |
  | 4 | status | rows marked `FAILED` are skipped |
  | 5 | operation amount | — |
  | 6 | operation currency | — |
  | 7 | amount | the signed amount used |
  | 8 | currency | — |
  | 9 | cashback | — |
  | 10 | bank category | stored, shown, and searchable |
  | 11 | MCC | stored |
  | 12 | description | categorization + display |
  | 13+ | bonuses, rounding, total | optional, ignored |

Lines with fewer than 12 columns, or an unparseable date or amount, are collected
as errors and reported back rather than silently dropped.

## Auto-categorization

Each category can carry a set of **keywords** (edit them from the budget grid).
The rules are a faithful port of the original spreadsheet's `FIND_CATEGORIES`:

1. Categories are split into **IN** and **OUT** rule sets by their group `kind`
   (income vs. expense).
2. A transaction's **sign** picks the rule set — a positive amount only matches
   income categories, a negative amount only matches expense ones.
3. The **first** category, in definition order, whose keyword is a
   case-insensitive substring of the description wins.

If nothing matches, the row comes in uncategorized and waits for you on the
Transactions page.

## Deduplication

Every transaction has a content hash — `sha1(date | amount | description)`. A row
counts as a duplicate of another only when all three match. Dedup happens at two
levels:

- **Preview** flags rows that already exist in the database, or that repeat
  within the pasted batch, so you can see what would be skipped.
- **Commit** re-checks on the server and never trusts the hash sent by the
  client. It counts how many copies of each hash the database already holds and
  how many appear in the batch, and inserts only the genuinely new ones. Re-importing
  an overlapping statement is therefore safe and idempotent — the same paste
  twice inserts nothing the second time.

Because dedup is by exact content, two truly identical transactions on the same
day for the same amount and description will be treated as one. That is rare with
real statements but worth knowing.

## The preview → commit flow

1. Open **Import statement** on the Transactions page and paste the text.
2. **Preview** shows the parsed rows with their auto-assigned category, marks
   duplicates, and lists any parse errors.
3. **Commit** inserts the fresh rows and reports how many were inserted and how
   many skipped.

Per-batch import logging with rollback and rule re-runs is planned in issue #22;
a richer multi-field rules engine (priorities, multiple actions, dry-run) in
issue #21.
