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
 * income(m) counts account opening balances too — money that sits on an account
 * before its first transaction is still money to budget.
 *
 * January chains from the previous year's December; the first year starts at 0.
 */

import { isTransfer } from "./transfers.js";

export function txKey(year, month, categoryId) {
    return `${year}-${month}-${categoryId}`;
}

/** Sum transaction amounts into a Map keyed by year-month-categoryId. */
export function buildTxIndex(transactions) {
    const index = new Map();
    for (const t of transactions) {
        // a leg keeps whatever category it carried before the merge only in the
        // transfers table, never here — but guard anyway, so no future path can
        // let moving money between accounts spend down an envelope
        if (t.categoryId == null || isTransfer(t)) continue;
        const year = +t.date.slice(0, 4);
        const month = +t.date.slice(5, 7);
        const key = txKey(year, month, t.categoryId);
        index.set(key, (index.get(key) ?? 0) + t.amount);
    }
    return index;
}

export function monthKey(year, month) {
    return `${year}-${month}`;
}

const OPENING_DATE = /^(\d{4})-(\d{1,2})(?:\D|$)/;

/** Map(accountId -> date of its earliest transaction). */
function firstTxDates(transactions) {
    const dates = new Map();
    for (const t of transactions ?? []) {
        const seen = dates.get(t.accountId);
        if (seen == null || t.date < seen) dates.set(t.accountId, t.date);
    }
    return dates;
}

/**
 * Sum account opening balances into a Map keyed by year-month.
 *
 * An opening balance is what the account held before its first recorded
 * transaction, so an account without an explicit opening date falls back to the
 * month of that first transaction. An account with neither — or one opened
 * before the range, or carrying an unparseable date — drops into the very first
 * month, so the money lands somewhere inside the range instead of vanishing.
 */
export function buildOpeningIndex(accounts, firstYear, transactions) {
    const index = new Map();
    if (!accounts?.length) return index;
    const firstTx = firstTxDates(transactions);
    for (const a of accounts) {
        const amount = a.openingBalance ?? 0;
        if (!amount) continue;
        const parsed = OPENING_DATE.exec(a.openingDate ?? firstTx.get(a.id) ?? "");
        let year = firstYear;
        let month = 1;
        if (parsed && +parsed[1] >= firstYear && +parsed[2] >= 1 && +parsed[2] <= 12) {
            year = +parsed[1];
            month = +parsed[2];
        }
        const key = monthKey(year, month);
        index.set(key, (index.get(key) ?? 0) + amount);
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
export function computeYear({
    year,
    categories,
    groupKindById,
    txIndex,
    budgetIndex,
    openingIndex,
    prev,
}) {
    const byCategory = new Map();
    const income = Array(12).fill(0);
    const budgetedTotal = Array(12).fill(0);
    const overspent = Array(12).fill(0);
    const available = Array(12).fill(0);

    const envelopeCats = [];
    for (const c of categories) {
        if (groupKindById.get(c.groupId) === "income") continue;
        envelopeCats.push(c);
    }

    for (const c of categories) {
        if (groupKindById.get(c.groupId) !== "income") continue;
        for (let m = 0; m < 12; m++) {
            income[m] += txIndex.get(txKey(year, m + 1, c.id)) ?? 0;
        }
    }

    for (let m = 0; m < 12; m++) {
        income[m] += openingIndex?.get(monthKey(year, m + 1)) ?? 0;
    }

    for (const c of envelopeCats) {
        const isExpense = groupKindById.get(c.groupId) === "expense";
        const months = [];
        let prevBalance = prev?.byCategory.get(c.id)?.[11]?.balance ?? 0;
        for (let m = 0; m < 12; m++) {
            const budgeted = budgetIndex.get(txKey(year, m + 1, c.id)) ?? 0;
            const outflows = txIndex.get(txKey(year, m + 1, c.id)) ?? 0;
            const balance = Math.max(prevBalance, 0) + budgeted + outflows;
            months.push({ budgeted, outflows, balance });
            budgetedTotal[m] += budgeted;
            if (isExpense && balance < 0) overspent[m] += balance;
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

/**
 * Where the chain has to start for a snapshot: Available carries forward from
 * the very first month, so a year left out is not merely hidden — everything
 * budgeted, earned and spent in it is dropped from every later year's running
 * total. `floor` is only a default for an empty account.
 */
export function firstBudgetYear(snapshot, floor) {
    if (!snapshot) return floor;
    const minTx = snapshot.transactions.reduce((m, t) => Math.min(m, +t.date.slice(0, 4)), floor);
    return snapshot.budgets.reduce((m, b) => Math.min(m, b.year), minTx);
}

/** Compute a chain of years [firstYear..lastYear]. Returns Map(year -> result). */
export function computeRange(snapshot, firstYear, lastYear) {
    const groupKindById = new Map(snapshot.groups.map((g) => [g.id, g.kind]));
    const txIndex = buildTxIndex(snapshot.transactions);
    const budgetIndex = buildBudgetIndex(snapshot.budgets);
    const openingIndex = buildOpeningIndex(snapshot.accounts, firstYear, snapshot.transactions);
    const results = new Map();
    let prev = null;
    for (let year = firstYear; year <= lastYear; year++) {
        const res = computeYear({
            year,
            categories: snapshot.categories,
            groupKindById,
            txIndex,
            budgetIndex,
            openingIndex,
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
