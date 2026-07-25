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

Under the hood a transfer is two rows — money out of the source, the same amount
into the destination — merged into one transfer entity. **Both rows stay real
transactions**, which is the point: the bank sends them itself, and keeping them
means a re-sync recognizes them instead of importing them again. Both legs are
uncategorized while merged, so a transfer never counts as income or expense —
your budget and analytics stay honest by construction, not by remembering to
exclude it. Net worth is unchanged, since the two legs cancel out.

### Transfers monori finds for you

Most transfers are never created by hand: the bank delivers both legs and monori
pairs them up. After every import and every sync it looks for an outflow and an
inflow of exactly the same amount on two different accounts. A pair a day or
less apart is merged straight away; a looser match is offered under **Find
transfers** on the Transactions page, where it can be confirmed or dismissed —
and a dismissed pair is never offered again.

A transfer with a fee (1000 out, 995 in) is never matched automatically, because
guessing which difference is a fee and which is a coincidence is not something
worth being wrong about. Merge those yourself from **Find transfers**.

### Splitting one apart

**Split into two transactions** in the transfer's row menu undoes the merge:
both transactions stay in the ledger and get back whatever categories they
carried before. Removing the money as well is **Delete both transactions**,
which is deliberately a separate action.

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
