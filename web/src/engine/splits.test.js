import { describe, expect, it } from "vitest";
import { effectiveTransactions } from "./splits.js";
import { buildTxIndex, txKey } from "./budget.js";
import { accountBalances, monthlySeries } from "./analytics.js";

describe("effectiveTransactions", () => {
    it("replaces a split container without changing the total", () => {
        const rows = effectiveTransactions([
            {
                id: 7,
                date: "2026-01-01",
                amount: -1000,
                categoryId: null,
                accountId: 2,
                splits: [
                    { id: 1, categoryId: 10, amount: -601, comment: "food" },
                    { id: 2, categoryId: 11, amount: -399, comment: "soap" },
                ],
            },
        ]);
        expect(rows).toHaveLength(2);
        expect(rows.map((row) => row.categoryId)).toEqual([10, 11]);
        expect(rows.reduce((sum, row) => sum + row.amount, 0)).toBe(-1000);
        expect(rows[0]).toMatchObject({ parentId: 7, splitId: 1, comment: "food" });
    });

    it("counts parts by category without double-counting the account balance", () => {
        const snapshot = {
            accounts: [{ id: 2, openingBalance: 0 }],
            groups: [{ id: 1, kind: "expense" }],
            categories: [
                { id: 10, groupId: 1 },
                { id: 11, groupId: 1 },
            ],
            transactions: [
                {
                    id: 7,
                    date: "2026-01-01",
                    amount: -1000,
                    categoryId: null,
                    accountId: 2,
                    transferId: null,
                    splits: [
                        { id: 1, categoryId: 10, amount: -601, comment: "" },
                        { id: 2, categoryId: 11, amount: -399, comment: "" },
                    ],
                },
            ],
        };
        const index = buildTxIndex(snapshot.transactions);
        expect(index.get(txKey(2026, 1, 10))).toBe(-601);
        expect(index.get(txKey(2026, 1, 11))).toBe(-399);
        expect(accountBalances(snapshot).get(2)).toBe(-1000);
        expect(monthlySeries(snapshot)).toEqual([["2026-01", { income: 0, expense: 1000 }]]);
    });
});
