import { describe, expect, it } from "vitest";
import {
    txKey,
    monthKey,
    buildTxIndex,
    buildBudgetIndex,
    buildOpeningIndex,
    computeYear,
    computeRange,
    firstBudgetYear,
    groupTotals,
} from "./budget.js";
import type { BudgetCell } from "../types.js";
import { buildSnapshot } from "../test/render.js";

describe("txKey", () => {
    it("joins year, month and category into a stable string key", () => {
        expect(txKey(2024, 3, 5)).toBe("2024-3-5");
        expect(txKey(2024, 12, 20)).toBe("2024-12-20");
    });
});

describe("buildTxIndex", () => {
    it("sums amounts per year-month-category and drops uncategorized rows", () => {
        const index = buildTxIndex([
            { date: "2024-03-15", amount: 100, categoryId: 5 },
            { date: "2024-03-20", amount: 50, categoryId: 5 },
            { date: "2024-04-01", amount: 70, categoryId: 5 },
            { date: "2024-03-02", amount: 999, categoryId: null },
        ]);
        expect(index.get(txKey(2024, 3, 5))).toBe(150);
        expect(index.get(txKey(2024, 4, 5))).toBe(70);
        // the uncategorized row must not create a key
        expect(index.size).toBe(2);
        expect(index.get(txKey(2024, 3, null))).toBeUndefined();
    });
});

describe("buildBudgetIndex", () => {
    it("maps each budget cell onto its year-month-category key", () => {
        const index = buildBudgetIndex([
            { year: 2024, month: 1, categoryId: 20, amount: 1000 },
            { year: 2024, month: 2, categoryId: 20, amount: 500 },
        ]);
        expect(index.get(txKey(2024, 1, 20))).toBe(1000);
        expect(index.get(txKey(2024, 2, 20))).toBe(500);
        expect(index.size).toBe(2);
    });
});

describe("buildOpeningIndex", () => {
    it("sums opening balances into the month an account opened", () => {
        const index = buildOpeningIndex(
            [
                { id: 1, openingBalance: 5000, openingDate: "2024-03-01" },
                { id: 2, openingBalance: 700, openingDate: "2024-03-20" },
                { id: 3, openingBalance: 100, openingDate: "2024-04-01" },
            ],
            2020,
        );
        expect(index.get(monthKey(2024, 3))).toBe(5700);
        expect(index.get(monthKey(2024, 4))).toBe(100);
        expect(index.size).toBe(2);
    });

    it("drops accounts opened before the range into the first month", () => {
        const index = buildOpeningIndex(
            [
                { id: 1, openingBalance: 5000, openingDate: "2018-06-01" },
                { id: 2, openingBalance: 300, openingDate: null },
            ],
            2020,
        );
        expect(index.get(monthKey(2020, 1))).toBe(5300);
        expect(index.size).toBe(1);
    });

    it("falls back to the month of the account's earliest transaction", () => {
        const index = buildOpeningIndex([{ id: 1, openingBalance: 5000 }], 2020, [
            { accountId: 1, date: "2024-05-20" },
            { accountId: 1, date: "2024-03-11" },
            { accountId: 2, date: "2021-01-04" },
        ]);
        expect(index.get(monthKey(2024, 3))).toBe(5000);
        expect(index.size).toBe(1);
    });

    it("prefers an explicit opening date over the earliest transaction", () => {
        const index = buildOpeningIndex(
            [{ id: 1, openingBalance: 5000, openingDate: "2022-07-01" }],
            2020,
            [{ accountId: 1, date: "2024-03-11" }],
        );
        expect(index.get(monthKey(2022, 7))).toBe(5000);
    });

    it("falls back to the first month on an unparseable or out-of-range date", () => {
        const index = buildOpeningIndex(
            [
                { id: 1, openingBalance: 100, openingDate: "not a date" },
                { id: 2, openingBalance: 200, openingDate: "2024-13-01" },
                { id: 3, openingBalance: 400, openingDate: "2024-00-01" },
            ],
            2020,
        );
        expect(index.get(monthKey(2020, 1))).toBe(700);
        expect(index.size).toBe(1);
    });

    it("accepts a date whose month is not zero-padded", () => {
        const index = buildOpeningIndex(
            [{ id: 1, openingBalance: 900, openingDate: "2024-2-01" }],
            2020,
        );
        expect(index.get(monthKey(2024, 2))).toBe(900);
    });

    it("keeps the earliest transaction when they arrive earliest-first too", () => {
        // the fallback must pick the minimum date regardless of iteration order;
        // an earliest-first list is the case a last-wins bug slips through
        const index = buildOpeningIndex([{ id: 1, openingBalance: 5000 }], 2020, [
            { accountId: 1, date: "2024-03-11" },
            { accountId: 1, date: "2024-05-20" },
        ]);
        expect(index.get(monthKey(2024, 3))).toBe(5000);
        expect(index.size).toBe(1);
    });

    it("honours the boundary months January and December of a later year", () => {
        // month 1 and month 12 are the inclusive edges of the 1..12 range; both
        // must stay in their own year, not fall back to the first month
        const index = buildOpeningIndex(
            [
                { id: 1, openingBalance: 100, openingDate: "2024-01-15" },
                { id: 2, openingBalance: 200, openingDate: "2024-12-05" },
            ],
            2020,
        );
        expect(index.get(monthKey(2024, 1))).toBe(100);
        expect(index.get(monthKey(2024, 12))).toBe(200);
        expect(index.has(monthKey(2020, 1))).toBe(false);
    });

    it("ignores zero balances and a missing accounts list", () => {
        expect(buildOpeningIndex([{ id: 1, openingBalance: 0 }], 2020).size).toBe(0);
        expect(buildOpeningIndex(undefined, 2020).size).toBe(0);
        expect(buildOpeningIndex([], 2020).size).toBe(0);
    });
});

// A hand-computed single-year scenario. cat 20 overspends in January
// (balance goes negative → overspent), then recovers in February; the negative
// December→January-style carry is clamped by max(prevBalance, 0).
const groups = [
    { id: 1, name: "Income", kind: "income" },
    { id: 2, name: "Expense", kind: "expense" },
];
const categories = [
    { id: 10, groupId: 1, name: "Job" },
    { id: 20, groupId: 2, name: "Groceries" },
];
const groupKindById = new Map(groups.map((g) => [g.id, g.kind]));

function yearOf(
    transactions: Parameters<typeof buildTxIndex>[0],
    budgets: BudgetCell[],
    prev: ReturnType<typeof computeYear> | null = null,
) {
    return computeYear({
        year: 2024,
        categories,
        groupKindById,
        txIndex: buildTxIndex(transactions),
        budgetIndex: buildBudgetIndex(budgets),
        prev,
    });
}

describe("computeYear", () => {
    const transactions = [
        { date: "2024-01-10", amount: 5000, categoryId: 10 },
        { date: "2024-01-15", amount: -1500, categoryId: 20 },
        { date: "2024-02-05", amount: -300, categoryId: 20 },
    ];
    const budgets = [
        { year: 2024, month: 1, categoryId: 20, amount: 1000 },
        { year: 2024, month: 2, categoryId: 20, amount: 1000 },
    ];
    const res = yearOf(transactions, budgets);

    it("accumulates income into the right month only", () => {
        expect(res.income).toEqual([5000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    });

    it("sums budgeted amounts per month", () => {
        expect(res.budgetedTotal).toEqual([1000, 1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    });

    it("carries the category balance with a max(prev, 0) reset", () => {
        const months = res.byCategory.get(20);
        // Jan: 0 + 1000 - 1500 = -500 (overspent)
        expect(months![0]).toEqual({ budgeted: 1000, outflows: -1500, balance: -500 });
        // Feb: max(-500, 0) + 1000 - 300 = 700 — the negative Jan balance is reset
        expect(months![1]).toEqual({ budgeted: 1000, outflows: -300, balance: 700 });
        // Mar onward: max(700, 0) + 0 + 0 = 700, held flat
        expect(months![2]!.balance).toBe(700);
        expect(months![11]!.balance).toBe(700);
    });

    it("records overspending only for months with a negative balance", () => {
        expect(res.overspent).toEqual([-500, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    });

    it("keeps goal activity out of expense overspend", () => {
        const goal = computeYear({
            year: 2024,
            categories: [{ id: 30, groupId: 3 }],
            groupKindById: new Map([[3, "goal"]]),
            txIndex: buildTxIndex([{ date: "2024-01-15", amount: -5_000, categoryId: 30 }]),
            budgetIndex: buildBudgetIndex([]),
            prev: null,
        });
        expect(goal.byCategory.get(30)![0]!.balance).toBe(-5_000);
        expect(goal.overspent[0]).toBe(0);
    });

    it("chains available-to-budget across months using prior overspent", () => {
        // Jan: 0 + 0 + 5000 - 1000 = 4000
        // Feb: 4000 + (-500 prev overspent) + 0 - 1000 = 2500
        // Mar: 2500 + 0 + 0 - 0 = 2500, held flat
        expect(res.available).toEqual([
            4000, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500, 2500,
        ]);
    });

    it("excludes income categories from byCategory", () => {
        expect(res.byCategory.has(10)).toBe(false);
        expect([...res.byCategory.keys()]).toEqual([20]);
    });
});

describe("computeRange carry-over between years", () => {
    it("feeds prior-year December balance and available into January", () => {
        const results = computeRange(
            buildSnapshot({
                groups,
                categories,
                transactions: [
                    { date: "2023-01-10", amount: 2000, categoryId: 10 },
                    { date: "2023-01-15", amount: -400, categoryId: 20 },
                    { date: "2024-01-15", amount: -900, categoryId: 20 },
                ],
                budgets: [
                    { year: 2023, month: 1, categoryId: 20, amount: 1000 },
                    { year: 2024, month: 1, categoryId: 20, amount: 500 },
                ],
            }),
            2023,
            2024,
        );

        const y2023 = results.get(2023);
        expect(y2023!.byCategory.get(20)![11]!.balance).toBe(600); // 1000 - 400, held flat
        expect(y2023!.available[11]).toBe(1000); // 2000 - 1000

        const y2024 = results.get(2024);
        // Jan 2024 balance = max(600 carried, 0) + 500 - 900 = 200
        expect(y2024!.byCategory.get(20)![0]!.balance).toBe(200);
        // Jan 2024 available = 1000 carried + 0 + 0 - 500 = 500
        expect(y2024!.available[0]).toBe(500);
    });
});

describe("opening balances in computeRange", () => {
    const snapshot = (accounts: NonNullable<Parameters<typeof buildSnapshot>[0]>["accounts"]) =>
        buildSnapshot({
            groups,
            categories,
            accounts,
            transactions: [{ date: "2024-02-10", amount: 5000, categoryId: 10 }],
            budgets: [{ year: 2024, month: 2, categoryId: 20, amount: 1000 }],
        });

    it("counts an opening balance as income of its opening month", () => {
        const res = computeRange(
            snapshot([{ id: 1, openingBalance: 3000, openingDate: "2024-02-01" }]),
            2024,
            2024,
        ).get(2024);
        expect(res!.income[1]).toBe(8000); // 5000 salary + 3000 opening
        expect(res!.available[1]).toBe(7000); // 8000 - 1000 budgeted
    });

    it("places a dateless opening balance with the account's first transaction", () => {
        const res = computeRange(
            snapshot([{ id: 1, openingBalance: 3000, openingDate: null }]),
            2024,
            2024,
        ).get(2024);
        expect(res!.income[0]).toBe(0);
        expect(res!.available[0]).toBe(0);
        expect(res!.income[1]).toBe(8000);
        expect(res!.available[1]).toBe(7000); // 3000 carried + 5000 - 1000
    });

    it("uses the account's first transaction when it has no opening date", () => {
        const res = computeRange(
            buildSnapshot({
                groups,
                categories,
                accounts: [{ id: 7, openingBalance: 3000, openingDate: null }],
                transactions: [{ date: "2024-02-10", amount: 5000, categoryId: 10, accountId: 7 }],
                budgets: [{ year: 2024, month: 2, categoryId: 20, amount: 1000 }],
            }),
            2024,
            2024,
        ).get(2024);
        expect(res!.income[0]).toBe(0);
        expect(res!.income[1]).toBe(8000);
        expect(res!.available[1]).toBe(7000);
    });

    it("leaves available untouched when every account opens at zero", () => {
        const res = computeRange(
            snapshot([{ id: 1, openingBalance: 0, openingDate: "2024-02-01" }]),
            2024,
            2024,
        ).get(2024);
        expect(res!.income[1]).toBe(5000);
        expect(res!.available[1]).toBe(4000);
    });
});

describe("groupTotals", () => {
    const g = [
        { id: 1, name: "Income", kind: "income" },
        { id: 2, name: "Expense", kind: "expense" },
    ];
    const cats = [
        { id: 10, groupId: 1, name: "Job" },
        { id: 20, groupId: 2, name: "Groceries" },
        { id: 21, groupId: 2, name: "Fun" },
    ];
    const res = computeYear({
        year: 2024,
        categories: cats,
        groupKindById: new Map(g.map((x) => [x.id, x.kind])),
        txIndex: buildTxIndex([
            { date: "2024-01-15", amount: -300, categoryId: 20 }, // balance 1000-300 = 700 (+)
            { date: "2024-01-16", amount: -900, categoryId: 21 }, // balance 100-900 = -800 (−)
        ]),
        budgetIndex: buildBudgetIndex([
            { year: 2024, month: 1, categoryId: 20, amount: 1000 },
            { year: 2024, month: 1, categoryId: 21, amount: 100 },
        ]),
        prev: null,
    });

    it("sums budgeted and outflows and only positive balances across the group", () => {
        const months = groupTotals(res, cats, 2);
        // Jan: budgeted 1000+100, outflows -300+-900, balance only the positive 700
        expect(months[0]).toEqual({ budgeted: 1100, outflows: -1200, balance: 700 });
        // Feb: cat20 carries 700 (+), cat21 resets to 0 (not > 0) → balance 700
        expect(months[1]).toEqual({ budgeted: 0, outflows: 0, balance: 700 });
    });

    it("ignores categories from other groups", () => {
        const months = groupTotals(res, cats, 2);
        // the income category (group 1) contributes nothing to group 2
        const janBudgetOnlyExpenses = 1100;
        expect(months[0]!.budgeted).toBe(janBudgetOnlyExpenses);
    });

    it("skips categories with no computed rows", () => {
        const ghost = [...cats, { id: 99, groupId: 2, name: "Never computed" }];
        const months = groupTotals(res, ghost, 2);
        // the ghost category has no byCategory entry and must not throw or change totals
        expect(months[0]!.budgeted).toBe(1100);
    });
});

describe("firstBudgetYear", () => {
    it("falls back to the floor with no snapshot or an empty one", () => {
        expect(firstBudgetYear(null, 2020)).toBe(2020);
        expect(firstBudgetYear({ transactions: [], budgets: [] }, 2020)).toBe(2020);
    });

    it("reaches back to the earliest transaction or budget a migration brought in", () => {
        const snapshot = {
            transactions: [{ date: "2018-07-04T00:00:00", amount: -100, categoryId: 1 }],
            budgets: [{ year: 2019, month: 1, categoryId: 1, amount: 500 }],
        };
        expect(firstBudgetYear(snapshot, 2020)).toBe(2018);
        expect(firstBudgetYear({ ...snapshot, transactions: [] }, 2020)).toBe(2019);
    });

    it("never starts later than the floor, so an empty later year is still shown", () => {
        const snapshot = {
            transactions: [{ date: "2026-01-01T00:00:00", amount: -100, categoryId: 1 }],
            budgets: [{ year: 2026, month: 1, categoryId: 1, amount: 500 }],
        };
        expect(firstBudgetYear(snapshot, 2020)).toBe(2020);
    });
});
