import { isTransfer } from "./transfers.js";
import { effectiveTransactions } from "./splits.js";
import type { Category, CategoryGroup, Id, Snapshot } from "../types.js";
import type { BudgetYearResult } from "./budget.js";

export interface MonthlyValue {
    income: number;
    expense: number;
}

export type MonthlySeries = Array<[string, MonthlyValue]>;

export interface CategoryMatrixRow {
    id: Id | null;
    groupId: Id | null;
    name: string;
    monthly: number[];
    total: number;
}

interface CategoryTotal {
    id: Id;
    groupId: Id;
    name: string;
    total: number;
}

interface LargestTransaction {
    amount: number;
    description: string;
    date: string;
}

interface DisciplineCell {
    budgeted: number;
    available: number;
    spent: number;
    ratio: number | null;
}

/**
 * Analytics helpers — pure functions over the snapshot, no I/O.
 * All money values are integer kopecks, mirroring the budget engine.
 * "Expense" numbers are returned positive (outflows negated) for charting.
 */

export function incomeGroupIdSet(groups: CategoryGroup[]): Set<Id> {
    return new Set(groups.filter((g) => g.kind === "income").map((g) => g.id));
}

/** Running balance per account = opening balance + its categorized
 * transactions + its transfer legs + reconcile adjustments.
 * An uncategorized row that is not a transfer is money the ledger has not
 * accepted yet — the budget ignores it, so the balance does too, and the two
 * views always move together. Returns Map(accountId -> kopecks). */
export function accountBalances(snapshot: Snapshot): Map<Id, number> {
    const balances = new Map(snapshot.accounts.map((a) => [a.id, a.openingBalance]));
    for (const t of effectiveTransactions(snapshot.transactions)) {
        if (!balances.has(t.accountId)) continue;
        if (t.categoryId == null && !isTransfer(t) && t.source !== "adjustment") continue;
        balances.set(t.accountId, (balances.get(t.accountId) ?? 0) + t.amount);
    }
    return balances;
}

/** Categorized transactions only, split into income/expense by group kind.
 * Returns sorted [key, {income, expense}] where key = 'YYYY-MM'. */
export function monthlySeries(snapshot: Snapshot): MonthlySeries {
    const incomeIds = incomeGroupIdSet(snapshot.groups);
    const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
    const map = new Map<string, MonthlyValue>();
    for (const t of effectiveTransactions(snapshot.transactions)) {
        if (isTransfer(t)) continue; // transfers never count as income/expense
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
export function yearTotals(monthly: MonthlySeries) {
    const byYear = new Map<string, MonthlyValue & { months: number }>();
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
export function weekdayProfile(snapshot: Snapshot, year: string): number[] {
    const incomeIds = incomeGroupIdSet(snapshot.groups);
    const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
    const sums = Array.from({ length: 7 }, (): number => 0);
    for (const t of effectiveTransactions(snapshot.transactions)) {
        if (!t.date.startsWith(year) || t.categoryId == null || t.amount >= 0) continue;
        if (isTransfer(t)) continue;
        const cat = catById.get(t.categoryId);
        if (!cat || incomeIds.has(cat.groupId)) continue;
        const dow = (new Date(t.date).getDay() + 6) % 7; // 0 = Monday
        sums[dow] = sums[dow]! - t.amount;
    }
    return sums;
}

/** Total expenses of one year bucketed by day of month. Returns [31] kopecks. */
export function dayOfMonthProfile(snapshot: Snapshot, year: string): number[] {
    const incomeIds = incomeGroupIdSet(snapshot.groups);
    const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
    const sums = Array.from({ length: 31 }, (): number => 0);
    for (const t of effectiveTransactions(snapshot.transactions)) {
        if (!t.date.startsWith(year) || t.categoryId == null || t.amount >= 0) continue;
        if (isTransfer(t)) continue;
        const cat = catById.get(t.categoryId);
        if (!cat || incomeIds.has(cat.groupId)) continue;
        const index = +t.date.slice(8, 10) - 1;
        sums[index] = sums[index]! - t.amount;
    }
    return sums;
}

/**
 * One year of categorized income or expenses as a category × month matrix,
 * ready to stack or plot.
 * Returns [{id, name, monthly[12], total}] sorted by yearly total, biggest
 * first, with everything past `limit` folded into a single trailing
 * `{id: null, name: "Other"}` row so a long tail of small categories cannot
 * turn the chart into an unreadable pile of slivers.
 *
 * `kind` defaults to expenses. Refunds are kept as the negative amounts they
 * are (same as monthlySeries), so a category's year adds up to exactly what
 * every other view reports for it.
 */
export function categoryYearMatrix(
    snapshot: Snapshot,
    year: string,
    { limit = 8, kind = "expense" }: { limit?: number; kind?: "expense" | "income" } = {},
): CategoryMatrixRow[] {
    const incomeIds = incomeGroupIdSet(snapshot.groups);
    const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
    const rows = new Map<Id, CategoryMatrixRow>();
    for (const t of effectiveTransactions(snapshot.transactions)) {
        if (!t.date.startsWith(year) || t.transferId != null || t.categoryId == null) continue;
        const cat = catById.get(t.categoryId);
        if (!cat || (kind === "income" ? !incomeIds.has(cat.groupId) : incomeIds.has(cat.groupId)))
            continue;
        let row = rows.get(cat.id);
        if (!row) {
            row = {
                id: cat.id,
                groupId: cat.groupId,
                name: cat.name,
                monthly: Array.from({ length: 12 }, (): number => 0),
                total: 0,
            };
            rows.set(cat.id, row);
        }
        const v = kind === "income" ? t.amount : -t.amount;
        row.monthly[+t.date.slice(5, 7) - 1]! += v;
        row.total += v;
    }
    const ranked = [...rows.values()]
        .filter((r) => r.total !== 0 || r.monthly.some((v) => v !== 0))
        .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
    if (ranked.length <= limit) return ranked;
    const other = {
        id: null,
        groupId: null,
        name: "Other",
        monthly: Array.from({ length: 12 }, (): number => 0),
        total: 0,
    };
    for (const r of ranked.slice(limit)) {
        for (let m = 0; m < 12; m++) other.monthly[m]! += r.monthly[m]!;
        other.total += r.total;
    }
    return [...ranked.slice(0, limit), other];
}

/** Totals by category across the entire ledger, sorted largest first.
 * The same categorized-only rule backs both all-time donut charts: transfers,
 * uncategorized transactions and deleted categories do not create a slice. */
export function categoryTotals(
    snapshot: Snapshot,
    { kind = "expense" }: { kind?: "expense" | "income" } = {},
): CategoryTotal[] {
    const incomeIds = incomeGroupIdSet(snapshot.groups);
    const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
    const rows = new Map<Id, CategoryTotal>();
    for (const t of effectiveTransactions(snapshot.transactions)) {
        if (isTransfer(t) || t.categoryId == null) continue;
        const cat = catById.get(t.categoryId);
        if (!cat || (kind === "income" ? !incomeIds.has(cat.groupId) : incomeIds.has(cat.groupId)))
            continue;
        let row = rows.get(cat.id);
        if (!row) {
            row = { id: cat.id, groupId: cat.groupId, name: cat.name, total: 0 };
            rows.set(cat.id, row);
        }
        row.total += kind === "income" ? t.amount : -t.amount;
    }
    return [...rows.values()]
        .filter((r) => r.total > 0)
        .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
}

/** Merchant key: strip trailing city/junk numbers, collapse whitespace, take a
 * stable prefix so "OZON ... MOSCOW" and "OZON ... MOSKVA G" group together. */
export function merchantKey(description: string): string {
    return description
        .toUpperCase()
        .replace(/[0-9*]+/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .split(" ")
        .slice(0, 3)
        .join(" ");
}

/** Top merchants by spend for a year: [{name, fullName, total, count}] desc. */
export function topMerchants(snapshot: Snapshot, year: string, limit = 10) {
    const incomeIds = incomeGroupIdSet(snapshot.groups);
    const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
    const sums = new Map<string, { fullName: string; total: number; count: number }>();
    for (const t of effectiveTransactions(snapshot.transactions)) {
        if (!t.date.startsWith(year) || t.categoryId == null || t.amount >= 0) continue;
        if (isTransfer(t)) continue;
        const cat = catById.get(t.categoryId);
        if (!cat || incomeIds.has(cat.groupId)) continue;
        const key = merchantKey(t.description) || "(no description)";
        let e = sums.get(key);
        if (!e) sums.set(key, (e = { fullName: t.description || key, total: 0, count: 0 }));
        e.total += -t.amount;
        e.count += 1;
    }
    return [...sums.entries()]
        .map(([name, v]) => ({ name, ...v }))
        .sort((a, b) => b.total - a.total)
        .slice(0, limit);
}

/** Expense-transaction stats for a year: count, median, largest.
 * Like every other analytics card, this uses only categorized expense rows:
 * uncategorized operations and transfer legs are not spending until they are
 * assigned to a real expense category. */
export function txStats(snapshot: Snapshot, year: string) {
    const incomeIds = incomeGroupIdSet(snapshot.groups);
    const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
    const amounts: number[] = [];
    let largest: LargestTransaction | null = null;
    for (const t of effectiveTransactions(snapshot.transactions)) {
        if (!t.date.startsWith(year) || t.amount >= 0) continue;
        if (isTransfer(t)) continue; // moving money is not spending
        if (t.categoryId == null) continue;
        const cat = catById.get(t.categoryId);
        if (!cat || incomeIds.has(cat.groupId)) continue;
        const v = -t.amount;
        amounts.push(v);
        if (!largest || v > largest.amount)
            largest = { amount: v, description: t.description, date: t.date };
    }
    amounts.sort((a, b) => a - b);
    const median = amounts.length ? amounts[Math.floor(amounts.length / 2)]! : 0;
    return { count: amounts.length, median, largest };
}

/** Income-transaction stats for a year: count, median, largest.
 * Only positive rows assigned to a real income category qualify; transfers and
 * uncategorized deposits stay out of every income metric until categorized. */
export function incomeStats(snapshot: Snapshot, year: string) {
    const incomeIds = incomeGroupIdSet(snapshot.groups);
    const catById = new Map(snapshot.categories.map((c) => [c.id, c]));
    const amounts: number[] = [];
    let largest: LargestTransaction | null = null;
    for (const t of effectiveTransactions(snapshot.transactions)) {
        if (!t.date.startsWith(year) || t.amount <= 0 || t.categoryId == null) continue;
        if (isTransfer(t)) continue;
        const cat = catById.get(t.categoryId);
        if (!cat || !incomeIds.has(cat.groupId)) continue;
        amounts.push(t.amount);
        if (!largest || t.amount > largest.amount)
            largest = { amount: t.amount, description: t.description, date: t.date };
    }
    amounts.sort((a, b) => a - b);
    const median = amounts.length ? amounts[Math.floor(amounts.length / 2)]! : 0;
    return { count: amounts.length, median, largest };
}

/**
 * Budget discipline for a year, from the engine's year result.
 * Per expense category: months[12] of {budgeted, available, spent, ratio|null}.
 *
 * A month is judged against the envelope, not against that month's budget line:
 * available = max(previous balance, 0) + budgeted, which is what the budget page
 * shows and what the engine spends down. Comparing spend to the bare monthly
 * budget double-counts every envelope that is saved up over months and emptied
 * in one — a year of vacation savings spent on one trip would report the whole
 * trip as an overrun even though the envelope covered all but the shortfall.
 * Since balance = available + outflows, the month's available is recovered from
 * the engine's own numbers with no extra state.
 *
 * ratio = spent / available; null when nothing is available and nothing spent.
 * Also aggregates hitRate (share of active months with spent <= available),
 * totalOverrun (kopecks the envelopes went negative by) and the worst category.
 */
export function disciplineMatrix(
    yearResult: BudgetYearResult,
    categories: Array<Pick<Category, "id" | "groupId" | "name">>,
    groups: CategoryGroup[],
    { upToMonth = 11 }: { upToMonth?: number } = {},
) {
    const incomeIds = incomeGroupIdSet(groups);
    type DisciplineCategory = Pick<Category, "id" | "groupId" | "name">;
    const rows: Array<{ category: DisciplineCategory; cells: DisciplineCell[] }> = [];
    let hits = 0,
        active = 0,
        totalOverrun = 0;
    let worst: { category: DisciplineCategory; overrun: number } | null = null;
    for (const c of categories) {
        if (incomeIds.has(c.groupId)) continue;
        const months = yearResult.byCategory.get(c.id);
        if (!months) continue;
        const cells: DisciplineCell[] = [];
        let any = false,
            catOverrun = 0;
        for (let m = 0; m < 12; m++) {
            const { budgeted, balance } = months[m]!;
            const spent = -months[m]!.outflows;
            const availableThisMonth = balance + spent;
            if (m > upToMonth) {
                cells.push({ budgeted: 0, available: 0, spent: 0, ratio: null });
                continue;
            }
            if (availableThisMonth <= 0 && spent <= 0) {
                cells.push({ budgeted, available: availableThisMonth, spent, ratio: null });
                continue;
            }
            any = true;
            const ratio = availableThisMonth > 0 ? spent / availableThisMonth : Infinity;
            cells.push({ budgeted, available: availableThisMonth, spent, ratio });
            active += 1;
            if (spent <= availableThisMonth) hits += 1;
            else {
                const over = spent - Math.max(availableThisMonth, 0);
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
