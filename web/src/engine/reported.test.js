import { describe, expect, it } from "vitest";
import { accountBalances, monthlySeries, txStats } from "./analytics.js";
import { buildTxIndex, txKey } from "./budget.js";
import { reported } from "./reported.js";

describe("reported", () => {
    it("prefers the reporting amount", () => {
        expect(reported({ amount: -10000, baseAmount: -300000 })).toBe(-300000);
    });

    it("falls back to the amount when there is no conversion", () => {
        // single-currency data, and anything written before base amounts existed
        expect(reported({ amount: -10000 })).toBe(-10000);
        expect(reported({ amount: -10000, baseAmount: null })).toBe(-10000);
    });

    it("does not mistake a zero conversion for a missing one", () => {
        expect(reported({ amount: 5, baseAmount: 0 })).toBe(0);
    });
});

/** A ledger with a ruble account and a lari one, 100.00 GEL = 3000.00 RUB. */
const snapshot = {
    groups: [
        { id: 1, kind: "income" },
        { id: 2, kind: "expense" },
    ],
    categories: [
        { id: 10, groupId: 1, name: "Job" },
        { id: 20, groupId: 2, name: "Cafes" },
    ],
    accounts: [
        { id: 1, currency: "RUB", openingBalance: 0 },
        { id: 2, currency: "GEL", openingBalance: 0 },
    ],
    transactions: [
        {
            id: 1,
            date: "2026-03-01",
            amount: 200000_00,
            baseAmount: 200000_00,
            currency: "RUB",
            accountId: 1,
            categoryId: 10,
            description: "Payroll",
        },
        {
            id: 2,
            date: "2026-03-05",
            amount: -1000_00,
            baseAmount: -1000_00,
            currency: "RUB",
            accountId: 1,
            categoryId: 20,
            description: "Coffee",
        },
        {
            id: 3,
            date: "2026-03-06",
            amount: -100_00,
            baseAmount: -3000_00,
            currency: "GEL",
            accountId: 2,
            categoryId: 20,
            description: "Khachapuri",
        },
    ],
    budgets: [],
};

describe("aggregation across currencies", () => {
    it("adds a category up in the reporting currency, not in raw amounts", () => {
        // 1000 rubles + 100 lari is 4000 rubles, never 1100 of anything
        const index = buildTxIndex(snapshot.transactions);
        expect(index.get(txKey(2026, 3, 20))).toBe(-4000_00);
    });

    it("reports the month with the foreign spend converted", () => {
        const [[month, totals]] = monthlySeries(snapshot);
        expect(month).toBe("2026-03");
        expect(totals.expense).toBe(4000_00);
        expect(totals.income).toBe(200000_00);
    });

    it("ranks and counts expenses by what they are worth", () => {
        const stats = txStats(snapshot, "2026");
        expect(stats.count).toBe(2);
        // the lari row is the smaller number and the larger expense
        expect(stats.largest.description).toBe("Khachapuri");
        expect(stats.largest.amount).toBe(3000_00);
    });

    it("leaves an account's own balance in its own currency", () => {
        // converting here would answer a question nobody asked: the lari card
        // holds lari, and that is what the accounts page prints
        const balances = accountBalances(snapshot);
        expect(balances.get(2)).toBe(-100_00);
        expect(balances.get(1)).toBe(199000_00);
    });
});
