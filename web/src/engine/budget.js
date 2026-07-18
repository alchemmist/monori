/**
 * Monori budget engine — pure functions, no I/O.
 *
 * All money values are integer kopecks. Semantics mirror the original
 * spreadsheet (YNAB-style envelope budgeting):
 *
 *   balance(cat, m)  = max(balance(cat, m-1), 0) + budgeted(cat, m) + outflows(cat, m)
 *   overspent(m)     = sum over expense categories of min(balance(cat, m), 0)
 *   available(m)     = available(m-1) + overspent(m-1) + income(m) - budgetedTotal(m)
 *
 * January chains from the previous year's December; the first year starts at 0.
 */

export function txKey(year, month, categoryId) {
    return `${year}-${month}-${categoryId}`;
}

/** Sum transaction amounts into a Map keyed by year-month-categoryId. */
export function buildTxIndex(transactions) {
    const index = new Map();
    for (const t of transactions) {
        if (t.categoryId == null) continue;
        const year = +t.date.slice(0, 4);
        const month = +t.date.slice(5, 7);
        const key = txKey(year, month, t.categoryId);
        index.set(key, (index.get(key) ?? 0) + t.amount);
    }
    return index;
}

/** Map 'year-month-categoryId' -> budgeted amount. */
export function buildBudgetIndex(budgets) {
    const index = new Map();
    for (const b of budgets) {
        index.set(txKey(b.year, b.month, b.categoryId), b.amount);
    }
    return index;
}

/**
 * Compute one year.
 * @param prev — result of computeYear for the previous year, or null.
 * @returns {year, byCategory: Map(catId -> months[12] of {budgeted, outflows, balance}),
 *           income[12], budgetedTotal[12], overspent[12], available[12]}
 */
export function computeYear({ year, categories, groupKindById, txIndex, budgetIndex, prev }) {
    const byCategory = new Map();
    const income = Array(12).fill(0);
    const budgetedTotal = Array(12).fill(0);
    const overspent = Array(12).fill(0);
    const available = Array(12).fill(0);

    const expenseCats = [];
    for (const c of categories) {
        if (groupKindById.get(c.groupId) === "income") continue;
        expenseCats.push(c);
    }

    for (const c of categories) {
        if (groupKindById.get(c.groupId) !== "income") continue;
        for (let m = 0; m < 12; m++) {
            income[m] += txIndex.get(txKey(year, m + 1, c.id)) ?? 0;
        }
    }

    for (const c of expenseCats) {
        const months = [];
        let prevBalance = prev?.byCategory.get(c.id)?.[11]?.balance ?? 0;
        for (let m = 0; m < 12; m++) {
            const budgeted = budgetIndex.get(txKey(year, m + 1, c.id)) ?? 0;
            const outflows = txIndex.get(txKey(year, m + 1, c.id)) ?? 0;
            const balance = Math.max(prevBalance, 0) + budgeted + outflows;
            months.push({ budgeted, outflows, balance });
            budgetedTotal[m] += budgeted;
            if (balance < 0) overspent[m] += balance;
            prevBalance = balance;
        }
        byCategory.set(c.id, months);
    }

    let prevAvailable = prev ? prev.available[11] : 0;
    let prevOverspent = prev ? prev.overspent[11] : 0;
    for (let m = 0; m < 12; m++) {
        available[m] = prevAvailable + prevOverspent + income[m] - budgetedTotal[m];
        prevAvailable = available[m];
        prevOverspent = overspent[m];
    }

    return { year, byCategory, income, budgetedTotal, overspent, available };
}

/** Compute a chain of years [firstYear..lastYear]. Returns Map(year -> result). */
export function computeRange(snapshot, firstYear, lastYear) {
    const groupKindById = new Map(snapshot.groups.map((g) => [g.id, g.kind]));
    const txIndex = buildTxIndex(snapshot.transactions);
    const budgetIndex = buildBudgetIndex(snapshot.budgets);
    const results = new Map();
    let prev = null;
    for (let year = firstYear; year <= lastYear; year++) {
        const res = computeYear({
            year,
            categories: snapshot.categories,
            groupKindById,
            txIndex,
            budgetIndex,
            prev,
        });
        results.set(year, res);
        prev = res;
    }
    return results;
}

/** Aggregate a year result per group: months[12] of {budgeted, outflows, balancePositive}. */
export function groupTotals(yearResult, categories, groupId) {
    const months = Array.from({ length: 12 }, () => ({ budgeted: 0, outflows: 0, balance: 0 }));
    for (const c of categories) {
        if (c.groupId !== groupId) continue;
        const rows = yearResult.byCategory.get(c.id);
        if (!rows) continue;
        for (let m = 0; m < 12; m++) {
            months[m].budgeted += rows[m].budgeted;
            months[m].outflows += rows[m].outflows;
            if (rows[m].balance > 0) months[m].balance += rows[m].balance;
        }
    }
    return months;
}
