import { describe, expect, it } from "vitest";
import { effectiveTransactions, splitPartTransaction } from "./splits.js";
import { buildTxIndex, txKey } from "./budget.js";
import { accountBalances, monthlySeries } from "./analytics.js";
import { buildSnapshot, tx } from "../test/render.js";

describe("effectiveTransactions", () => {
    it("accepts an empty ledger and a standalone split without sibling rows", () => {
        expect(effectiveTransactions()).toEqual([]);
        const parent = tx(12, { amount: -2, baseAmount: -3 });
        delete parent.splits;
        const part = { id: 1, categoryId: 10, amount: -1, comment: "" };
        expect(splitPartTransaction(parent, part).baseAmount).toBe(-2);
    });

    it("builds the shared synthetic row shape", () => {
        expect(
            splitPartTransaction(
                tx(7, {
                    accountId: 2,
                    splits: [{ id: 1, categoryId: 10, amount: -601, comment: "food" }],
                }),
                { id: 1, categoryId: 10, amount: -601, comment: "food" },
            ),
        ).toMatchObject({
            id: "7:1",
            parentId: 7,
            splitId: 1,
            accountId: 2,
            categoryId: 10,
            amount: -601,
            comment: "food",
            splits: [],
        });
    });

    it("replaces a split container without changing the total", () => {
        const rows = effectiveTransactions([
            tx(7, {
                date: "2026-01-01",
                amount: -1000,
                baseAmount: -3333,
                accountAmount: -1000,
                categoryId: null,
                accountId: 2,
                splits: [
                    { id: 1, categoryId: 10, amount: -601, comment: "food" },
                    { id: 2, categoryId: 11, amount: -399, comment: "soap" },
                ],
            }),
        ]);
        expect(rows).toHaveLength(2);
        expect(rows.map((row) => row.categoryId)).toEqual([10, 11]);
        expect(rows.reduce((sum, row) => sum + row.amount, 0)).toBe(-1000);
        expect(rows.reduce((sum, row) => sum + (row.baseAmount ?? 0), 0)).toBe(-3333);
        expect(rows.reduce((sum, row) => sum + (row.accountAmount ?? 0), 0)).toBe(-1000);
        expect(rows[0]).toMatchObject({ parentId: 7, splitId: 1, comment: "food" });
    });

    it("counts parts by category without double-counting the account balance", () => {
        const snapshot = buildSnapshot({
            accounts: [{ id: 2, openingBalance: 0 }],
            groups: [{ id: 1, kind: "expense" }],
            categories: [
                { id: 10, groupId: 1 },
                { id: 11, groupId: 1 },
            ],
            transactions: [
                tx(7, {
                    date: "2026-01-01",
                    amount: -1000,
                    categoryId: null,
                    accountId: 2,
                    transferId: null,
                    splits: [
                        { id: 1, categoryId: 10, amount: -601, comment: "" },
                        { id: 2, categoryId: 11, amount: -399, comment: "" },
                    ],
                }),
            ],
        });
        const index = buildTxIndex(snapshot.transactions);
        expect(index.get(txKey(2026, 1, 10))).toBe(-601);
        expect(index.get(txKey(2026, 1, 11))).toBe(-399);
        expect(accountBalances(snapshot).get(2)).toBe(-1000);
        expect(monthlySeries(snapshot)).toEqual([["2026-01", { income: 0, expense: 1000 }]]);
    });

    it("uses ties-to-even allocation before assigning the final remainder", () => {
        const rows = effectiveTransactions([
            tx(9, {
                amount: -2,
                baseAmount: -3,
                splits: [
                    { id: 1, categoryId: 10, amount: -1, comment: "" },
                    { id: 2, categoryId: 11, amount: -1, comment: "" },
                ],
            }),
        ]);
        expect(rows.map((row) => row.baseAmount)).toEqual([-2, -1]);
    });
    it.each([-1, 1])("preserves split signs and totals when rounding (%s)", (sign) => {
        const parent = tx(9, {
            amount: sign * 6,
            baseAmount: sign * 4,
            accountAmount: sign * 2,
            splits: Array.from({ length: 6 }, (_, index) => ({
                id: index + 1,
                categoryId: 10 + index,
                amount: sign,
                comment: "",
            })),
        });
        const rows = effectiveTransactions([parent]);
        expect([...buildTxIndex([parent]).values()]).toEqual(rows.map((row) => row.baseAmount));
        expect(rows.map((row) => row.baseAmount)).toEqual(
            [1, 0, 1, 1, 0, 1].map((value) => (value === 0 ? 0 : sign * value)),
        );
        expect(rows.reduce((sum, row) => sum + (row.accountAmount ?? 0), 0)).toBe(sign * 2);
        expect(rows.every((row) => sign * (row.accountAmount ?? 0) >= 0)).toBe(true);
        expect(parent.splits!.map((part) => splitPartTransaction(parent, part).baseAmount)).toEqual(
            rows.map((row) => row.baseAmount),
        );
    });
    it("conserves large supported integer totals in views and budget indexing", () => {
        const parent = tx(10, {
            date: "2026-01-01",
            amount: 2686651785705924,
            baseAmount: 7652238166763927,
            splits: [
                { id: 1, categoryId: 10, amount: 2686651785705923, comment: "" },
                { id: 2, categoryId: 11, amount: 1, comment: "" },
            ],
        });
        const rows = effectiveTransactions([parent]);
        expect(rows.reduce((sum, row) => sum + (row.baseAmount ?? 0), 0)).toBe(parent.baseAmount);
        expect([...buildTxIndex([parent]).values()].reduce((sum, value) => sum + value, 0)).toBe(
            parent.baseAmount,
        );
    });
});
