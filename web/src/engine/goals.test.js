import { describe, expect, it } from "vitest";
import { goalProgress } from "./goals.js";

describe("goalProgress", () => {
    it("derives active, achieved and archived states from an envelope", () => {
        const goal = { id: 7, goalTarget: 10_000, archived: false };
        const budgets = [
            { categoryId: 7, year: 2026, month: 1, amount: 4_900 },
            { categoryId: 7, year: 2026, month: 4, amount: 5_100 },
            { categoryId: 8, year: 2026, month: 1, amount: 99_000 },
        ];
        expect(goalProgress(goal, budgets, 2026, 3)).toEqual({
            funded: 4_900,
            target: 10_000,
            percent: 49,
            status: "active",
        });
        expect(goalProgress(goal, budgets, 2026, 4).status).toBe("achieved");
        expect(goalProgress({ ...goal, archived: true }, budgets, 2026, 1).status).toBe("archived");
    });

    it("counts allocations from earlier years but not from a later year or month", () => {
        const goal = { id: 7, goalTarget: 100_000, archived: false };
        const budgets = [
            { categoryId: 7, year: 2025, month: 12, amount: 1_000 }, // earlier year → counts
            { categoryId: 7, year: 2026, month: 2, amount: 2_000 }, // earlier month → counts
            { categoryId: 7, year: 2026, month: 6, amount: 4_000 }, // later month, same year → excluded
            { categoryId: 7, year: 2027, month: 1, amount: 8_000 }, // later year → excluded
        ];
        expect(goalProgress(goal, budgets, 2026, 3).funded).toBe(3_000);
    });

    it("stays active with a zero percent when there is no target", () => {
        const goal = { id: 7, goalTarget: 0, archived: false };
        const budgets = [{ categoryId: 7, year: 2026, month: 1, amount: 5_000 }];
        // a goal without a target can never be "achieved" and never divides by it
        expect(goalProgress(goal, budgets, 2026, 3)).toMatchObject({ percent: 0, status: "active" });
        expect(goalProgress({ ...goal, goalTarget: undefined }, budgets, 2026, 3).percent).toBe(0);
    });

    it("counts deallocations but ignores unrelated categories", () => {
        const progress = goalProgress(
            { id: 1, goalTarget: 5_000 },
            [
                { categoryId: 1, year: 2026, month: 1, amount: 1_000 },
                { categoryId: 1, year: 2026, month: 2, amount: -1_800 },
                { categoryId: 2, year: 2026, month: 2, amount: 5_000 },
            ],
            2026,
            2,
        );
        expect(progress.funded).toBe(-800);
        expect(progress.percent).toBe(0);
    });
});
