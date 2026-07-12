/**
 * Analytics helpers — pure functions over the snapshot, no I/O.
 * All money values are integer kopecks, mirroring the budget engine.
 * "Expense" numbers are returned positive (outflows negated) for charting.
 */

export function incomeGroupIdSet(groups) {
  return new Set(groups.filter((g) => g.kind === "income").map((g) => g.id));
}

/** Categorized transactions only, split into income/expense by group kind.
 * Returns sorted [key, {income, expense}] where key = 'YYYY-MM'. */
export function monthlySeries(snapshot) {
  const incomeIds = incomeGroupIdSet(snapshot.groups);
  const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
  const map = new Map();
  for (const t of snapshot.transactions) {
    if (t.categoryId == null) continue;
    const cat = catById.get(t.categoryId);
    if (!cat) continue;
    const key = t.date.slice(0, 7);
    let e = map.get(key);
    if (!e) map.set(key, (e = { income: 0, expense: 0 }));
    if (incomeIds.has(cat.groupId)) e.income += t.amount;
    else e.expense += -t.amount;
  }
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
}

/** Per-year totals from a monthlySeries result. Returns sorted
 * [{year, income, expense, net, savingsRate, avgExpense, months}]. */
export function yearTotals(monthly) {
  const byYear = new Map();
  for (const [key, v] of monthly) {
    const year = key.slice(0, 4);
    let e = byYear.get(year);
    if (!e) byYear.set(year, (e = { income: 0, expense: 0, months: 0 }));
    e.income += v.income;
    e.expense += v.expense;
    e.months += 1;
  }
  return [...byYear.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([year, v]) => ({
      year,
      income: v.income,
      expense: v.expense,
      net: v.income - v.expense,
      savingsRate: v.income > 0 ? ((v.income - v.expense) / v.income) * 100 : null,
      avgExpense: v.months > 0 ? v.expense / v.months : 0,
      months: v.months,
    }));
}

/** Total expenses of one year bucketed by weekday. Returns [7] kopecks, Monday first. */
export function weekdayProfile(snapshot, year) {
  const incomeIds = incomeGroupIdSet(snapshot.groups);
  const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
  const sums = Array(7).fill(0);
  for (const t of snapshot.transactions) {
    if (!t.date.startsWith(year) || t.categoryId == null || t.amount >= 0) continue;
    const cat = catById.get(t.categoryId);
    if (!cat || incomeIds.has(cat.groupId)) continue;
    const dow = (new Date(t.date).getDay() + 6) % 7; // 0 = Monday
    sums[dow] += -t.amount;
  }
  return sums;
}

/** Total expenses of one year bucketed by day of month. Returns [31] kopecks. */
export function dayOfMonthProfile(snapshot, year) {
  const incomeIds = incomeGroupIdSet(snapshot.groups);
  const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
  const sums = Array(31).fill(0);
  for (const t of snapshot.transactions) {
    if (!t.date.startsWith(year) || t.categoryId == null || t.amount >= 0) continue;
    const cat = catById.get(t.categoryId);
    if (!cat || incomeIds.has(cat.groupId)) continue;
    sums[+t.date.slice(8, 10) - 1] += -t.amount;
  }
  return sums;
}

/** Merchant key: strip trailing city/junk numbers, collapse whitespace, take a
 * stable prefix so "OZON ... MOSCOW" and "OZON ... MOSKVA G" group together. */
export function merchantKey(description) {
  return description
    .toUpperCase()
    .replace(/[0-9*]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .slice(0, 3)
    .join(" ");
}

/** Top merchants by spend for a year: [{name, total, count}] desc. */
export function topMerchants(snapshot, year, limit = 10) {
  const incomeIds = incomeGroupIdSet(snapshot.groups);
  const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
  const sums = new Map();
  for (const t of snapshot.transactions) {
    if (!t.date.startsWith(year) || t.categoryId == null || t.amount >= 0) continue;
    const cat = catById.get(t.categoryId);
    if (!cat || incomeIds.has(cat.groupId)) continue;
    const key = merchantKey(t.description) || "(no description)";
    let e = sums.get(key);
    if (!e) sums.set(key, (e = { total: 0, count: 0 }));
    e.total += -t.amount;
    e.count += 1;
  }
  return [...sums.entries()]
    .map(([name, v]) => ({ name, ...v }))
    .sort((a, b) => b.total - a.total)
    .slice(0, limit);
}

/** Expense-transaction stats for a year: count, median, largest. */
export function txStats(snapshot, year) {
  const incomeIds = incomeGroupIdSet(snapshot.groups);
  const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
  const amounts = [];
  let largest = null;
  for (const t of snapshot.transactions) {
    if (!t.date.startsWith(year) || t.categoryId == null || t.amount >= 0) continue;
    const cat = catById.get(t.categoryId);
    if (!cat || incomeIds.has(cat.groupId)) continue;
    const v = -t.amount;
    amounts.push(v);
    if (!largest || v > largest.amount)
      largest = { amount: v, description: t.description, date: t.date };
  }
  amounts.sort((a, b) => a - b);
  const median = amounts.length ? amounts[Math.floor(amounts.length / 2)] : 0;
  return { count: amounts.length, median, largest };
}

/**
 * Budget discipline for a year, from the engine's year result.
 * Per expense category: months[12] of {budgeted, spent, ratio|null}.
 * ratio = spent / budgeted; null when nothing budgeted and nothing spent.
 * Also aggregates hitRate (share of active months with spent <= budgeted),
 * totalOverrun (kopecks overspent beyond budget) and the worst category.
 */
export function disciplineMatrix(yearResult, categories, groups, { upToMonth = 11 } = {}) {
  const incomeIds = incomeGroupIdSet(groups);
  const rows = [];
  let hits = 0,
    active = 0,
    totalOverrun = 0;
  let worst = null;
  for (const c of categories) {
    if (incomeIds.has(c.groupId)) continue;
    const months = yearResult.byCategory.get(c.id);
    if (!months) continue;
    const cells = [];
    let any = false,
      catOverrun = 0;
    for (let m = 0; m < 12; m++) {
      const budgeted = months[m].budgeted;
      const spent = -months[m].outflows;
      if (m > upToMonth) {
        cells.push({ budgeted: 0, spent: 0, ratio: null });
        continue;
      }
      if (budgeted <= 0 && spent <= 0) {
        cells.push({ budgeted, spent, ratio: null });
        continue;
      }
      any = true;
      const ratio = budgeted > 0 ? spent / budgeted : Infinity;
      cells.push({ budgeted, spent, ratio });
      active += 1;
      if (spent <= budgeted) hits += 1;
      else {
        const over = spent - Math.max(budgeted, 0);
        totalOverrun += over;
        catOverrun += over;
      }
    }
    if (!any) continue;
    if (catOverrun > 0 && (!worst || catOverrun > worst.overrun)) {
      worst = { category: c, overrun: catOverrun };
    }
    rows.push({ category: c, cells });
  }
  return { rows, hitRate: active > 0 ? (hits / active) * 100 : null, totalOverrun, worst };
}
