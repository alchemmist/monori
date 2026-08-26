import { describe, expect, it } from "vitest";
import { PALETTE, SERIES, fmtNum } from "./chartTheme.js";

describe("chartTheme", () => {
    describe("PALETTE", () => {
        it("is a set of theme-backed color variables", () => {
            expect(PALETTE).toHaveLength(12);
            for (const [index, color] of PALETTE.entries()) {
                expect(color).toBe(`var(--m-chart-${index + 1})`);
            }
            expect(new Set(PALETTE).size).toBe(PALETTE.length);
        });

        it("leads with the themed accent so the first series carries the brand color", () => {
            expect(PALETTE[0]).toBe("var(--m-chart-1)");
        });

        it("keeps chart semantics inside the chart color system", () => {
            expect(SERIES).toMatchObject({
                accent: "var(--m-chart-accent)",
                income: "var(--m-chart-income)",
                expense: "var(--m-chart-expense)",
                warning: "var(--m-chart-warning)",
            });
        });
    });

    describe("fmtNum", () => {
        it("renders nothing for a missing value", () => {
            expect(fmtNum(null)).toBe("");
            expect(fmtNum(undefined)).toBe("");
        });

        it("groups thousands with the ru-RU space separator", () => {
            expect(fmtNum(1000)).toMatch(/^1\s000$/);
            expect(fmtNum(1234567)).toMatch(/^1\s234\s567$/);
        });

        it("rounds to whole units", () => {
            expect(fmtNum(1234.5)).toMatch(/^1\s235$/);
            expect(fmtNum(1234.4)).toMatch(/^1\s234$/);
        });

        it("keeps the sign on negatives and formats zero plainly", () => {
            expect(fmtNum(-1234)).toMatch(/^-1\s234$/);
            expect(fmtNum(0)).toBe("0");
        });
    });
});
