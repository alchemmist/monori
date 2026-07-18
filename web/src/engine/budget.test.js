import { describe, expect, it } from "vitest";
import {
    txKey,
    buildTxIndex,
    buildBudgetIndex,
    computeYear,
    computeRange,
    groupTotals,
} from "./budget.js";

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

function yearOf(transactions, budgets, prev = null) {
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
        expect(months[0]).toEqual({ budgeted: 1000, outflows: -1500, balance: -500 });
        // Feb: max(-500, 0) + 1000 - 300 = 700 — the negative Jan balance is reset
        expect(months[1]).toEqual({ budgeted: 1000, outflows: -300, balance: 700 });
        // Mar onward: max(700, 0) + 0 + 0 = 700, held flat
        expect(months[2].balance).toBe(700);
        expect(months[11].balance).toBe(700);
    });

    it("records overspending only for months with a negative balance", () => {
        expect(res.overspent).toEqual([-500, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
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
            {
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
            },
            2023,
            2024,
        );

        const y2023 = results.get(2023);
        expect(y2023.byCategory.get(20)[11].balance).toBe(600); // 1000 - 400, held flat
        expect(y2023.available[11]).toBe(1000); // 2000 - 1000

        const y2024 = results.get(2024);
        // Jan 2024 balance = max(600 carried, 0) + 500 - 900 = 200
        expect(y2024.byCategory.get(20)[0].balance).toBe(200);
        // Jan 2024 available = 1000 carried + 0 + 0 - 500 = 500
        expect(y2024.available[0]).toBe(500);
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
        expect(months[0].budgeted).toBe(janBudgetOnlyExpenses);
    });

    it("skips categories with no computed rows", () => {
        const ghost = [...cats, { id: 99, groupId: 2, name: "Never computed" }];
        const months = groupTotals(res, ghost, 2);
        // the ghost category has no byCategory entry and must not throw or change totals
        expect(months[0].budgeted).toBe(1100);
    });
});
