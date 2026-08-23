import { describe, it, expect } from "vitest";
import { mergeCategories, unionKeywords } from "./mergeCategories.js";
import { buildSnapshot } from "./test/render.js";

const snap = () =>
    buildSnapshot({
        categories: [
            { id: 1, name: "Cafe", keywords: "starbucks|shokoladnitsa" },
            { id: 2, name: "Coffee", keywords: "cofix|STARBUCKS" },
            { id: 3, name: "Rent", keywords: "" },
        ],
        budgets: [
            { categoryId: 1, year: 2026, month: 1, amount: 500 },
            { categoryId: 2, year: 2026, month: 1, amount: 300 },
            { categoryId: 2, year: 2026, month: 2, amount: 700 },
            { categoryId: 3, year: 2026, month: 1, amount: 900 },
        ],
        transactions: [
            { id: 10, categoryId: 2 },
            { id: 11, categoryId: 1 },
            { id: 12, categoryId: null },
        ],
    });

describe("unionKeywords", () => {
    it("dedupes case-insensitively, target keys first", () => {
        expect(unionKeywords("starbucks|shokoladnitsa", "cofix|STARBUCKS")).toBe(
            "starbucks|shokoladnitsa|cofix",
        );
    });

    it("copes with empty sides and stray spacing", () => {
        expect(unionKeywords("", "tea")).toBe("tea");
        expect(unionKeywords("coffee", "")).toBe("coffee");
        expect(unionKeywords(null, undefined)).toBe("");
        expect(unionKeywords(" a | b ", "b|c")).toBe("a|b|c");
    });
});

describe("mergeCategories", () => {
    it("moves transactions to the target", () => {
        const out = mergeCategories(snap(), 2, 1);
        expect(out.transactions.map((t) => t.categoryId)).toEqual([1, 1, null]);
    });

    it("drops the source and unions its keywords into the target", () => {
        const out = mergeCategories(snap(), 2, 1);
        expect(out.categories.map((c) => c.id)).toEqual([1, 3]);
        expect(out.categories[0]!.keywords).toBe("starbucks|shokoladnitsa|cofix");
    });

    it("sums budgets month by month instead of dropping them", () => {
        const out = mergeCategories(snap(), 2, 1);
        const mine = out.budgets.filter((b) => b.categoryId === 1);
        expect(mine).toEqual([
            { categoryId: 1, year: 2026, month: 1, amount: 800 },
            { categoryId: 1, year: 2026, month: 2, amount: 700 },
        ]);
    });

    it("leaves other categories and their budgets untouched", () => {
        const out = mergeCategories(snap(), 2, 1);
        expect(out.budgets.filter((b) => b.categoryId === 3)).toEqual([
            { categoryId: 3, year: 2026, month: 1, amount: 900 },
        ]);
        // an unrelated category keeps exactly its own keywords, it is not handed
        // the source's
        expect(out.categories.find((c) => c.id === 3)!.keywords).toBe("");
    });

    it("leaves no budget behind under the source category", () => {
        const out = mergeCategories(snap(), 2, 1);
        expect(out.budgets.some((b) => b.categoryId === 2)).toBe(false);
    });

    it("does not mutate the input snapshot", () => {
        const before = snap();
        mergeCategories(before, 2, 1);
        expect(before).toEqual(snap());
    });

    it("is a no-op for a self-merge or an unknown side", () => {
        const before = snap();
        expect(mergeCategories(before, 2, 2)).toBe(before);
        expect(mergeCategories(before, 99, 1)).toBe(before);
        expect(mergeCategories(before, 2, 99)).toBe(before);
    });
});
