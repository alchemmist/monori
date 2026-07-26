# Budgeting

monori is an **envelope** budget. Every month you hand out the money you have to
named envelopes (categories); spending draws each envelope down; whatever is left
rolls forward into the same envelope next month. This is the YNAB model, and the
math is identical to the spreadsheet monori grew from.

## The building blocks

- **Groups** — top-level buckets with a `kind` of either `income` or `expense`.
  Categories in an income group count as money coming in; categories in an
  expense group are envelopes you spend from.
- **Categories** — the envelopes themselves. Each belongs to one group, has an
  order, an optional set of import keywords, and an archived flag.
- **Budgets** — one number per (category, year, month): how much you assigned to
  that envelope that month. A budget of zero is the same as no budget — the cell
  is cleared.
- **Transactions** — signed amounts (negative is an outflow) that land in a
  category and a month by their date.

## How the math works

All budgeting math lives in `web/src/engine/budget.js` as pure functions and runs
in the browser off the single snapshot. Three formulas describe everything.

For each expense category, month by month:

```text
balance(cat, m) = max(balance(cat, m-1), 0) + budgeted(cat, m) + outflows(cat, m)
```

That is: carry the envelope's leftover from last month (but never carry a
negative — an overspent envelope starts the next month at zero, not in the red),
add what you assigned this month, then subtract what you spent (`outflows` are
already negative).

Across all expense categories in a month:

```text
overspent(m) = sum over expense categories of min(balance(cat, m), 0)
```

`overspent` is the total that went red this month — the money you spent that no
envelope had covered.

And the pool you have left to assign — "to be budgeted":

```text
available(m) = available(m-1) + overspent(m-1) + income(m) - budgetedTotal(m)
```

Each month starts with last month's leftover pool, is *reduced* by last month's
overspending (you have to make it up), grows by this month's income, and shrinks
by everything you assigned this month. This chains across month and year
boundaries: December of one year feeds January of the next, so the whole history
is one continuous ledger.

A positive `available` means you still have money to hand out; a negative one
means you have assigned more than you have.

`income(m)` is not only income transactions: an account's **opening balance**
counts as income of the month the account opened, because money that sits on an
account before its first transaction is still money you have to budget. Without
an opening date the balance falls back to the month of the account's earliest
transaction; with neither (or a date that predates the grid) it contributes to
the very first month of the range, so its money is never lost.

## Using the budget grid

The **Budget** page renders this as a grid of categories (grouped) against
months. A year selector at the top picks which year you are looking at.

**View mode** — a Year / Month toggle:

- **Year** shows all twelve months at once. A density control switches between:
  - **Full** — assigned, activity, and running balance for every cell;
  - **Plan** — just what you assigned;
  - **Actual** — activity and balance, for reviewing what happened.
- **Month** zooms into a single month (picked with a month selector) for
  focused editing, with summary cards on top:
  - **To be budgeted** — the `available` pool at the end of the month;
  - **Income** — total income for the month;
  - **Overspent** — the uncovered total this month.

Editing is inline: click a budget cell and type an amount. Changes are applied
optimistically in the UI and saved to the backend immediately, so the balances
and the "to be budgeted" figure recompute as you type.

## Managing categories and groups

From the budget grid you can:

- **create** groups and categories,
- **rename** them and change a category's group,
- set a category's **keywords** for auto-categorization (see
  [Importing](importing.md)),
- **archive** a category to hide it from day-to-day use while keeping its history,
- **reorder** groups and categories,
- **delete** a category. The dialog always asks where its transactions should go,
  and the answer decides what kind of delete it is:
  - **into another category** — for when the same thing ended up split over two
    names ("Cafe" and "Coffee"). The transactions move across, the two keyword
    sets are unioned so auto-categorization keeps working, and the monthly
    budgets follow the spending: a month both categories planned is summed, a
    month only the deleted one planned is carried over as it is. Only categories
    of the same kind are offered — income with income, expense with expense —
    because moving history across the line would flip its sign.
  - **leave uncategorized** — for a category that should never have existed. The
    transactions stay, without a category, and the budget history goes with it.

  Either way the dialog spells out what will happen before you confirm, and
  neither can be undone.

A group can only be deleted once it has no categories.
