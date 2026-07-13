# Dashboard & analytics

The **Dashboard** page has two halves: a set of charts and KPIs up top, and a
full annual report below. Everything is derived in the browser from the snapshot
by the pure functions in `web/src/engine/analytics.js`, using **categorized**
transactions only — uncategorized rows and income categories are handled
appropriately per chart, and income is excluded from expense analysis.

## KPIs

A row of headline numbers:

- **Net year to date** — income minus expense so far this year.
- **Savings rate** — the share of income kept, colored by sign.
- **Avg monthly spend** — mean expense over the last 12 months.
- **Spent this month**, **Daily rate** (per-day pace this month), and a
  **Month forecast** projecting the month's total from the current pace.

## Charts

- **Income vs. expense trend** — a time series over a selectable range: 6 months,
  1 / 3 / 5 years, year-to-date, or all time (with a custom range picker).
- **Category donut** — spending by category for a chosen year.
- **Month-over-month** and **plan vs. fact** views comparing budgeted against
  actual per month.

Charts are rendered with the Gravity UI charts library and share a theme so
colors line up across views. Each is wrapped in an error boundary so a single
bad chart cannot take the page down.

## The annual report

Pick a year and get a structured review:

- **Savings rate** for the year.
- **Budget discipline** — the hit rate, i.e. the share of active category-months
  that came in at or under budget (green ≥ 80%, amber ≥ 60%, red below), the total
  overrun in rubles, and the worst category by overrun. A per-category ×
  per-month grid (`disciplineMatrix`) shows budgeted vs. spent for every cell.
- **Plan vs. fact** for the year and **expenses year over year**.
- **Yearly report, all time** — a table of income, expense, net, and savings rate
  per year.
- **Spending patterns**:
  - **By weekday** — the expense distribution across Monday–Sunday.
  - **By day of month** — a 1–31 profile of when in the month money goes out.
- **Top merchants** — the top 10 by spend, with counts. Merchants are grouped by a
  normalized key (uppercased description, digits stripped, first few words).
- **Transaction stats** — count, median expense, and largest single transaction.

## Notes on the numbers

- Everything is computed off categorized transactions; if a chart looks light,
  check for uncategorized rows on the [Transactions](transactions.md) page.
- All money flows through as integer kopecks and is formatted to rubles only for
  display, so totals reconcile exactly with the budget grid.

A dedicated, configurable **Reports** builder (label-selector charts, chart-type
switching) is planned in issue #18; a spending-activity calendar heatmap in
issue #14.
