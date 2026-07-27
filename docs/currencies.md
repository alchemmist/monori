# Currencies

monori holds money in more than one currency, and it keeps the two questions
that raises strictly apart:

- **What was this?** — every transaction records the currency it was spent in.
  A lari row says 28 ₾, always, on every screen that shows the row itself.
- **What is it all worth?** — every total is expressed in one **reporting
  currency**, converted at the rate for each transaction's own date.

Adding a lari row to a ruble row is the one thing the app will never do.

## What is stored

Each transaction carries two amounts:

| Field | What it is |
| ------- | ------------ |
| `amount` | the money as it was spent, in `currency` |
| `baseAmount` | the same money in the reporting currency, at the rate for the transaction's date |

`amount` is what the transactions page prints. `baseAmount` is what the budget,
the dashboard, analytics and the workbook export add up — nothing else may be
summed across accounts.

The conversion is frozen when the row is written. A rate published next month
never changes what last month cost.

## Accounts

An account is held in one currency. New transactions on it are recorded in that
currency, and its balance is shown in it — an account's balance is its own
money, so converting it would answer a question nobody asked.

Re-labelling an account's currency does not rewrite its history: rows already
filed keep what they were spent in. Only what comes next is denominated anew.

The Accounts page shows a converted **Total** only when the accounts are not all
held in the reporting currency — otherwise it would repeat a sum the eye can
already do.

## The reporting currency

Set it in **Settings → Currency**. Changing it reprices the whole ledger: every
`baseAmount` is recomputed at the rate for its own transaction's date. The
transactions themselves do not move.

Rubles by default.

## Exchange rates

Rates come from the Bank of Russia's daily feed and are stored per day, quoted
in **rubles per unit**. One pivot means any pair of currencies is two lookups:

```text
amount in B = amount in A × rate(A) ÷ rate(B)
```

Looking up a rate for a date takes the latest publication no later than it —
which is exactly what was in force, since the feed only moves on business days.
For a transaction older than anything stored, it reaches forward to the earliest
rate held instead. If nothing is stored at all, a snapshot bundled with the app
is used, and the settings screen labels it as such, so an offline monori still
adds up and says so.

**Settings → Currency** lists every rate with the day it was published and where
it came from. *Fetch today* pulls the current publication and catches up on any
recent days that are missing. Clicking a rate lets you type one in by hand — for
a day the feed never published, or a currency it does not carry. Either way,
every transaction that rate priced is repriced.

Reading rates is everyone's; changing them is an admin's. What a currency was
worth on a day is one shared fact — the table has no owner column, so a
hand-set rate moves every user's totals at once. The per-user case, *my bank
converted at its own rate*, is recorded where it belongs: on the transfer, as
the amount that actually arrived.

## Transfers between currencies

A transfer is two linked rows, each in its own account's currency. When those
differ, the two magnitudes differ too, and the dialog asks for both: the amount
sent and the amount received.

The received field is filled in at the day's rate as a starting point. Replace it
with what actually landed — a bank converts at its own rate, not the central
bank's, and what arrived is the fact worth recording.

Auto-detection never pairs two currencies. 100 lari leaving one account and 100
rubles arriving on another are not the same money, however alike the numbers
look, so a cross-currency transfer is always linked deliberately.

## Importing

A pasted statement's currency column is read as the pair it is printed as: the
settlement amount and the currency it settled in. A row with no currency — or
with a code monori does not know — is taken as the account's, since nothing
could price an unknown one and its converted value would silently be the raw
number.

Workbook migration already splits accounts by currency — a `*2947 · USD` slot
can only be pointed at a USD account — and now records that currency on every
row it imports. See [Migrating from a spreadsheet](migration.md).

## Which currencies

A short curated list rather than all of ISO 4217: RUB, USD, EUR, GBP, CHF, KZT,
BYN, GEL, AMD, TRY, AED, CNY, RSD. Every one has two minor units, which is what
lets monori keep storing money as an integer count of them.

Adding one means adding it in two places — `server/app/currencies.py` and
`web/src/currencies.js` — and a test holds the two lists to each other.
