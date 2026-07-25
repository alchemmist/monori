import { describe, expect, it } from "vitest";
import { mergeTransactions } from "./mergeTransactions.js";

const tx = (id, date, extra = {}) => ({ id, date, ...extra });

describe("mergeTransactions", () => {
    it("keeps the canonical date, id order when an older chunk lands", () => {
        const loaded = [tx(9, "2026-03-01"), tx(10, "2026-03-02")];
        const chunk = [tx(3, "2026-01-01"), tx(4, "2026-02-01")];
        expect(mergeTransactions(loaded, chunk).map((t) => t.id)).toEqual([3, 4, 9, 10]);
    });

    it("interleaves a chunk that overlaps the loaded range", () => {
        const loaded = [tx(2, "2026-01-02"), tx(5, "2026-01-05")];
        const chunk = [tx(1, "2026-01-01"), tx(3, "2026-01-03"), tx(9, "2026-01-09")];
        expect(mergeTransactions(loaded, chunk).map((t) => t.id)).toEqual([1, 2, 3, 5, 9]);
    });

    it("breaks same-date ties by id", () => {
        const loaded = [tx(4, "2026-01-01")];
        const chunk = [tx(2, "2026-01-01"), tx(7, "2026-01-01")];
        expect(mergeTransactions(loaded, chunk).map((t) => t.id)).toEqual([2, 4, 7]);
    });

    it("drops duplicates and keeps the loaded copy, so optimistic edits survive", () => {
        const loaded = [tx(1, "2026-01-01", { categoryId: 42 })];
        const chunk = [tx(1, "2026-01-01", { categoryId: null })];
        const out = mergeTransactions(loaded, chunk);
        expect(out).toHaveLength(1);
        expect(out[0].categoryId).toBe(42);
    });

    it("returns the same array when there is nothing new", () => {
        const loaded = [tx(1, "2026-01-01")];
        expect(mergeTransactions(loaded, [])).toBe(loaded);
        expect(mergeTransactions(loaded, [tx(1, "2026-01-01")])).toBe(loaded);
    });

    it("handles an empty ledger", () => {
        const chunk = [tx(1, "2026-01-01")];
        expect(mergeTransactions([], chunk)).toEqual(chunk);
    });
});
