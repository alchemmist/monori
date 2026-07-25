# Migrating from a spreadsheet

If you have been budgeting in a YNAB-style spreadsheet — the kind monori's own
Excel export produces — you can move your whole history into monori in one go:
category groups, categories with their keywords, every transaction, and the
budget grid for every year. No retyping.

The importer and the exporter share one format definition, so a monori export
re-imports cleanly: **export → import round-trips** groups, categories,
transactions and budgets. One field does not survive the trip: a transaction's
**comment** is written to the workbook and read back off it, but the importer
does not store it — re-importing an export leaves comments blank.

## Running a migration

1. Download your workbook as `.xlsx` (in Google Sheets: *File → Download →
   Microsoft Excel*).
2. Open **Settings → Migrate from spreadsheet** and pick the file.
3. Review the preview: how many groups, categories, transactions and budget
   cells were found, plus any warnings and unparseable rows.
4. **Map accounts.** The workbook only knows card markers (like `*2947`) or
   account names; monori asks which of your accounts each marker should land
   on. Create the accounts first if they don't exist yet.
   A marker that carries rows in more than one currency is asked about once per
   currency — `*2947 · USD` is its own line — and only accounts held in that
   currency are offered. Without a USD account there is nothing to pick, so the
   import stays blocked rather than filing dollars as rubles.
5. Pick a **budget policy** for cells that already have a value in monori:
   *Overwrite* takes the workbook's number, *Keep mine* leaves yours untouched.
6. Import. The result screen shows exactly what was created and what was
   skipped as a duplicate.

## How a workbook is read

There is one reader, and it never asks what kind of file it was handed. A
workbook is measured, not classified: every stage looks at what is actually on
the sheets and does the most it can with it. That is why the same code reads a
file monori exported and the hand-kept spreadsheet monori grew from, and why a
workbook that is a bit of both still works.

- **`Transactions`** — the only sheet a workbook must have. Columns are resolved
  by meaning, not position or language: an operation datetime (`Дата операции`
  or `Date`), a status, a signed amount, and optionally card, currency, bank
  category, MCC, description, `Monori Category`, `Account`, `Comment`. A row is
  read as long as it can say **when** it happened and **for how much**;
  everything else is a bonus.
  - The **amount** is what actually moved: *Сумма платежа* when the sheet has
    that column, the operation amount otherwise. One card operation split across
    categories repeats its full total on every part and carries each part's real
    share in the payment amount — sometimes as a formula (`=-48480+16990`),
    which is added up on import. Every part becomes its own transaction with its
    own category; only rows identical down to that share count as duplicates.
  - The **category** is copied literally. A workbook that names a category
    column in its header is taken at its word. The live spreadsheet doesn't name
    it and keeps two: what the keyword rules guessed and what actually counts —
    that guess accepted, or a label typed over it. Only the second is what its
    totals are built from, so of the unnamed columns between the last known bank
    header and the keyword table the reader takes the **fullest** one, which is
    that column in the live sheet and the only one in a monori export. A blank
    stays uncategorized: workbook keywords are saved for future imports and
    syncs, never applied retroactively to its historical rows.
- **`Categories`**, when a workbook states its structure outright — a table of
  `Sort Order`, `Category Group`, `Category`, `Keywords`, with `▲`/`▼` glyphs or
  an `IN`/`OUT` group table marking direction. Keywords (pipe-separated, like
  `lenta|okey`) come along and immediately power auto-categorization. Stated
  structure is believed: the year grids may then add budgets to it, but not
  invent categories it left out. A sheet by that name whose rows say nothing the
  reader recognizes counts as absent — the live spreadsheet has one of those.
- **Year sheets** (`2024`, `2025`, `2024_archive`, …) — the budget grid:
  categories down the side, `Budgeted / Outflows / Balance` per month. The
  header row is found by content, so it doesn't matter which row it sits on or
  whether it says `Budgeted` or `Бюджет`. Where no `Categories` sheet stated the
  structure, the grid's own sections supply it. Only *Budgeted* is imported as a
  budget, and only where it is non-zero; outflows and balances are derived
  values monori recomputes — but they are still read, because they are what a
  month without rows gets rebuilt from.
  - A year with an `_archive` sheet is read from that sheet alone: a plain
    sheet for the same year is a working copy of history and is ignored.
  - The year before the earliest live one is the **seam** — where the archived
    past hands over to the months that still have rows. Its December is where
    every carried-over balance is squared up (see the reconciliation rule
    below), and its successor's *Not budgeted* / *Не заложено* header cell
    fixes the running Available at that hand-over.
- **`DashData`** — derived analytics; ignored on import for the same reason.
- A category a row names that no sheet lists is still imported, on the income
  side if everything filed under it came in and the expense side otherwise.
  Dropping it would silently uncategorize that row.

Unknown sheets and unrecognized rows are skipped with a warning, never a
silent drop.

## What the importer guarantees

- **Idempotent.** Every transaction is hashed
  (`account|date|amount|description`), and rows whose hash already exists on the
  target account are skipped. The corrections the importer derives are computed
  from the workbook alone, so they hash the same way on a second run: running
  the same migration twice imports nothing the second time.
- **Merges by name.** A group or category that already exists in monori (same
  name, same group) is reused, not duplicated. Existing categories keep their
  keywords.
- **Resolves categories against your whole account.** A name the workbook's own
  structure doesn't list is still matched against every category you already
  have, ignoring case and extra spaces. Only a name that matches nothing is left
  uncategorized — reported, never guessed at.
- **Batched.** Each migration lands as an import batch per account, tagged as
  coming from a workbook. (Browsing and rolling back those batches is not built
  yet — see issue #22.)
- **Non-OK rows are skipped** (declined or held operations) and reported as a
  preview warning.
- **Reconciles the grid explicitly.** Every source row is copied unchanged.
  When the year grid's cached income, outflow or balance differs, the importer
  adds a dated correction transaction for the difference. This preserves
  hand-maintained adjustments such as `+10,000` in formulas and makes the
  imported grid equal the spreadsheet without rewriting its original rows.
  Reconciliation runs month by month from the earliest sheet up to the last
  month with real activity — a row, a cached outflow, or income. Budgeted-only
  months beyond that are left alone: budgeting ahead is normal, and squaring up
  against a future month's carry residue would invent future-dated
  transactions.

## What the preview warnings mean

A warning is never a failure — it is the reader saying what it did with
something ambiguous. The ones a hand-kept workbook usually raises:

- **`Categories: no category rows recognized … structure taken from the year
  grids`** — the sheet named `Categories` is laid out in some other way, so the
  structure came from the sections of the year grids instead. The categories in
  the count above the warnings are the ones that will be created; nothing was
  lost.
- **`history: N transactions stand in for months …`** — the archive years hold
  no rows at all, only monthly totals. One transaction per category per month
  stands in for them so those years still add up. They show up in monori as
  ordinary rows named after their category.
- **`reconciliation: N adjustment transactions …`** — the year grid and its
  rows differed, so N explicit correction transactions were added. The source
  rows themselves were not changed.
- **`seam: N carry corrections at YYYY-12`** — the same thing at the hand-over
  between the archived years and the first one that still has rows: N
  corrections so every category starts the live era on the balance the
  spreadsheet says it had.
- **`N category names in the sheet match nothing in monori`** — raised on the
  result screen, not the preview: those rows were imported uncategorized rather
  than filed under a guess. Re-running the
  migration will not fix them: the rows already exist and get skipped as
  duplicates, so categorize them in monori instead.
- **`verify: the sheet's own Available differs …`** — the sheet's running
  Available versus the one recomputed from everything imported. A difference
  that stays roughly constant month over month is money carried in from before
  the earliest sheet, not a mis-read row. Transactions and budgets are imported
  either way; only this one running total starts from a different point.
- **`Transactions: N rows in USD`** — see the currency rule in step 4 above.

## Limits

- Amounts keep their face value and are never converted: a row in USD goes to a
  USD account as 95.78 USD. Cross-currency arithmetic (a single total across
  accounts in different currencies) is still out of scope.
- Transfers between accounts arrive as two ordinary transactions — link them
  in monori afterwards if you want them netted out of analytics.
