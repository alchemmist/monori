# Accounts & transfers

An **account** is where money physically sits — a bank card, cash in your pocket,
a savings account. Every transaction belongs to exactly one account, so monori
can track each balance separately and tell your app's picture apart from any one
bank's.

If you are upgrading from an earlier version, there is nothing to do: a default
**T-Bank** account is created automatically and all your existing transactions
are moved onto it, so everything behaves exactly as before.

## Managing accounts

Accounts live on the **Accounts** page in the sidebar. Each one has:

- a **name** (unique),
- a **type** — `card`, `cash`, `savings`, or `other`,
- an **icon and color** — a glyph from a small set plus a color; the glyph and
  its tile take the color (a saturated glyph over a translucent tint). Or **upload
  a custom image** (e.g. a bank logo), which replaces the glyph and color
  entirely. An image you've already added to one account can be reused on another
  straight from the picker. Uploaded images are downscaled and stored inline with
  the account,
- a **currency** — a label only for now; monori is single-currency and does no
  conversion (full multi-currency is tracked in issue #29),
- an **opening balance** — what the account held before the first recorded
  transaction.

From the list you can create, rename, reorder, **archive** (hide without
deleting), and delete accounts. Deleting an account asks where its transactions
should go: they are reassigned to another account, never lost. Because every
transaction must belong to an account, you cannot delete a non-empty account
without choosing a target, and you cannot delete the last remaining account.

### Balances

An account's **running balance** is its opening balance plus the sum of every
transaction on it — transfers included. Balances show as cards on the
[Dashboard](dashboard-analytics.md), and the dashboard's account filter narrows
every chart to a single account.

## Transfers

Moving money between two of your own accounts is a **transfer**, not spending.
Use the **Transfer** button on the Transactions page: pick the source and
destination accounts, an amount, and a date.

Under the hood a transfer is two linked rows — money out of the source, the same
amount into the destination — sharing a transfer id and shown with a **transfer**
badge. Both legs are deliberately uncategorized, so a transfer never counts as
income or expense: your budget and analytics stay honest by construction, not by
remembering to exclude it. Deleting a transfer removes both legs together.

## Reconcile

**Reconcile** checks monori against reality. Open it from an account's menu on
the Accounts page, enter the account's **actual bank balance**, and monori posts a single
`adjustment` transaction for the difference so the computed balance matches your
bank. If the two already agree, nothing is posted.

## Budgets stay global

Accounts do not change budgeting. Envelopes and the budget math span all accounts
together — a budget is about *what* the money is for (its category and month),
not *where* it sits. Accounts answer "how much is in each place"; budgets answer
"how much is allotted to each purpose".
