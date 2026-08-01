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

import type { Account, BudgetCell, Category, Id, Snapshot, Transaction } from "../types.js";

type BudgetTransaction = Pick<Transaction, "date" | "amount" | "categoryId"> &
    Partial<Pick<Transaction, "transferId" | "splits">>;
type OpeningAccount = Pick<Account, "id" | "openingBalance"> &
    Partial<Pick<Account, "openingDate">>;
type AccountTransaction = Pick<Transaction, "accountId" | "date">;
type BudgetCategory = Pick<Category, "id" | "groupId">;

export interface BudgetMonth {
    budgeted: number;
    outflows: number;
    balance: number;
}

export interface BudgetYearResult {
    year: number;
    byCategory: Map<Id, BudgetMonth[]>;
    income: number[];
    budgetedTotal: number[];
    overspent: number[];
    available: number[];
}

interface ComputeYearInput {
    year: number;
    categories: BudgetCategory[];
    groupKindById: Map<Id, string>;
    txIndex: Map<string, number>;
    budgetIndex: Map<string, number>;
    openingIndex?: Map<string, number>;
    prev: BudgetYearResult | null;
}

export function txKey(year: number, month: number, categoryId: Id | null): string {
    return `${year}-${month}-${categoryId}`;
}

/** Sum transaction amounts into a Map keyed by year-month-categoryId. */
export function buildTxIndex(transactions: BudgetTransaction[]): Map<string, number> {
    const index = new Map<string, number>();
    const effective = transactions.flatMap((transaction) =>
        transaction.splits?.length
            ? transaction.splits.map((part) => ({
                  ...transaction,
                  categoryId: part.categoryId,
                  amount: part.amount,
              }))
            : transaction,
    );
    for (const t of effective) {
        // a leg keeps whatever category it carried before the merge only in the
        // transfers table, never here — but guard anyway, so no future path can
        // let moving money between accounts spend down an envelope
        if (t.categoryId == null || t.transferId != null) continue;
        const year = +t.date.slice(0, 4);
        const month = +t.date.slice(5, 7);
        const key = txKey(year, month, t.categoryId);
        index.set(key, (index.get(key) ?? 0) + t.amount);
    }
    return index;
}

export function monthKey(year: number, month: number): string {
    return `${year}-${month}`;
}

const OPENING_DATE = /^(\d{4})-(\d{1,2})(?:\D|$)/;

/** Map(accountId -> date of its earliest transaction). */
function firstTxDates(transactions: AccountTransaction[]): Map<Id, string> {
    const dates = new Map<Id, string>();
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
export function buildOpeningIndex(
    accounts: OpeningAccount[] | undefined,
    firstYear: number,
    transactions: AccountTransaction[] = [],
): Map<string, number> {
    const index = new Map<string, number>();
    if (!accounts?.length) return index;
    const firstTx = firstTxDates(transactions);
    for (const a of accounts) {
        const amount = a.openingBalance ?? 0;
        if (!amount) continue;
        const parsed = OPENING_DATE.exec(a.openingDate ?? firstTx.get(a.id) ?? "");
        let year = firstYear;
        let month = 1;
        if (parsed && +parsed[1]! >= firstYear && +parsed[2]! >= 1 && +parsed[2]! <= 12) {
            year = +parsed[1]!;
            month = +parsed[2]!;
        }
        const key = monthKey(year, month);
        index.set(key, (index.get(key) ?? 0) + amount);
    }
    return index;
}

/** Map 'year-month-categoryId' -> budgeted amount. */
export function buildBudgetIndex(budgets: BudgetCell[]): Map<string, number> {
    const index = new Map<string, number>();
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
}: ComputeYearInput): BudgetYearResult {
    const byCategory = new Map<Id, BudgetMonth[]>();
    const income = Array<number>(12).fill(0);
    const budgetedTotal = Array<number>(12).fill(0);
    const overspent = Array<number>(12).fill(0);
    const available = Array<number>(12).fill(0);

    const envelopeCats: BudgetCategory[] = [];
    for (const c of categories) {
        if (groupKindById.get(c.groupId) === "income") continue;
        envelopeCats.push(c);
    }

    for (const c of categories) {
        if (groupKindById.get(c.groupId) !== "income") continue;
        for (let m = 0; m < 12; m++) {
            income[m]! += txIndex.get(txKey(year, m + 1, c.id)) ?? 0;
        }
    }

    for (let m = 0; m < 12; m++) {
        income[m]! += openingIndex?.get(monthKey(year, m + 1)) ?? 0;
    }

    for (const c of envelopeCats) {
        const isExpense = groupKindById.get(c.groupId) === "expense";
        const months: BudgetMonth[] = [];
        let prevBalance = prev?.byCategory.get(c.id)?.[11]?.balance ?? 0;
        for (let m = 0; m < 12; m++) {
            const budgeted = budgetIndex.get(txKey(year, m + 1, c.id)) ?? 0;
            const outflows = txIndex.get(txKey(year, m + 1, c.id)) ?? 0;
            const balance = Math.max(prevBalance, 0) + budgeted + outflows;
            months.push({ budgeted, outflows, balance });
            budgetedTotal[m]! += budgeted;
            if (isExpense && balance < 0) overspent[m]! += balance;
            prevBalance = balance;
        }
        byCategory.set(c.id, months);
    }

    let prevAvailable = prev ? prev.available[11]! : 0;
    let prevOverspent = prev ? prev.overspent[11]! : 0;
    for (let m = 0; m < 12; m++) {
        available[m] = prevAvailable + prevOverspent + income[m]! - budgetedTotal[m]!;
        prevAvailable = available[m]!;
        prevOverspent = overspent[m]!;
    }

    return { year, byCategory, income, budgetedTotal, overspent, available };
}

/**
 * Where the chain has to start for a snapshot: Available carries forward from
 * the very first month, so a year left out is not merely hidden — everything
 * budgeted, earned and spent in it is dropped from every later year's running
 * total. `floor` is only a default for an empty account.
 */
export function firstBudgetYear(
    snapshot: {
        transactions: Array<Pick<Transaction, "date">>;
        budgets: Array<Pick<BudgetCell, "year">>;
    } | null,
    floor: number,
): number {
    if (!snapshot) return floor;
    const minTx = snapshot.transactions.reduce((m, t) => Math.min(m, +t.date.slice(0, 4)), floor);
    return snapshot.budgets.reduce((m, b) => Math.min(m, b.year), minTx);
}

/** Compute a chain of years [firstYear..lastYear]. Returns Map(year -> result). */
export function computeRange(
    snapshot: Snapshot,
    firstYear: number,
    lastYear: number,
): Map<number, BudgetYearResult> {
    const groupKindById = new Map(snapshot.groups.map((g) => [g.id, g.kind]));
    const txIndex = buildTxIndex(snapshot.transactions);
    const budgetIndex = buildBudgetIndex(snapshot.budgets);
    const openingIndex = buildOpeningIndex(snapshot.accounts, firstYear, snapshot.transactions);
    const results = new Map<number, BudgetYearResult>();
    let prev: BudgetYearResult | null = null;
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
export function groupTotals(
    yearResult: BudgetYearResult,
    categories: BudgetCategory[],
    groupId: Id,
): BudgetMonth[] {
    const months = Array.from({ length: 12 }, () => ({ budgeted: 0, outflows: 0, balance: 0 }));
    for (const c of categories) {
        if (c.groupId !== groupId) continue;
        const rows = yearResult.byCategory.get(c.id);
        if (!rows) continue;
        for (let m = 0; m < 12; m++) {
            months[m]!.budgeted += rows[m]!.budgeted;
            months[m]!.outflows += rows[m]!.outflows;
            if (rows[m]!.balance > 0) months[m]!.balance += rows[m]!.balance;
        }
    }
    return months;
}
