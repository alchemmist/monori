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

    it("counts deallocations but ignores unrelated categories", () => {
        expect(
            goalProgress(
                { id: 1, goalTarget: 5_000 },
                [
                    { categoryId: 1, year: 2026, month: 1, amount: 1_000 },
                    { categoryId: 1, year: 2026, month: 2, amount: -800 },
                    { categoryId: 2, year: 2026, month: 2, amount: 5_000 },
                ],
                2026,
                2,
            ).funded,
        ).toBe(200);
    });
});
