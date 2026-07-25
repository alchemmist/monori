import { describe, expect, it } from "vitest";
import { PALETTE, SERIES, fmtNum, cartesian } from "./chartTheme.js";

describe("chartTheme", () => {
    describe("PALETTE", () => {
        it("exports an array of colors", () => {
            expect(Array.isArray(PALETTE)).toBe(true);
        });

        it("has 12 colors", () => {
            expect(PALETTE).toHaveLength(12);
        });

        it("all values are valid hex colors", () => {
            const hexRegex = /^#[0-9a-f]{6}$/i;
            PALETTE.forEach((color) => {
                expect(color).toMatch(hexRegex);
            });
        });

        it("first color is orange (brand accent)", () => {
            expect(PALETTE[0]).toBe("#ef5a17");
        });

        it("contains distinct colors", () => {
            const unique = new Set(PALETTE);
            expect(unique.size).toBe(PALETTE.length);
        });
    });

    describe("SERIES", () => {
        it("has income color defined", () => {
            expect(SERIES.income).toBe("var(--m-income)");
        });

        it("has expense color defined", () => {
            expect(SERIES.expense).toBe("var(--m-expense)");
        });

        it("has accent color defined", () => {
            expect(SERIES.accent).toBe("var(--m-accent)");
        });

        it("has warning color defined", () => {
            expect(SERIES.warning).toBe("var(--m-warning)");
        });

        it("has hint color defined", () => {
            expect(SERIES.hint).toBe("var(--g-color-text-hint)");
        });

        it("has secondary color defined", () => {
            expect(SERIES.secondary).toBe("var(--g-color-text-secondary)");
        });

        it("all values are CSS variables", () => {
            Object.values(SERIES).forEach((value) => {
                expect(value).toMatch(/^var\(--/);
            });
        });
    });

    describe("fmtNum", () => {
        it("returns empty string for null", () => {
            expect(fmtNum(null)).toBe("");
        });

        it("returns empty string for undefined", () => {
            expect(fmtNum(undefined)).toBe("");
        });

        it("formats positive integers with locale formatting", () => {
            expect(fmtNum(1234)).toMatch(/1\s234/);
        });

        it("formats large numbers with space separators", () => {
            expect(fmtNum(1234567)).toMatch(/1\s234\s567/);
        });

        it("rounds decimal values", () => {
            expect(fmtNum(1234.5)).toMatch(/1\s235/);
            expect(fmtNum(1234.4)).toMatch(/1\s234/);
        });

        it("handles negative numbers", () => {
            expect(fmtNum(-1234)).toMatch(/-1\s234/);
        });

        it("formats zero", () => {
            expect(fmtNum(0)).toBe("0");
        });

        it("uses Russian locale formatting", () => {
            const result = fmtNum(1000);
            expect(result).toMatch(/1\s000/);
        });
    });

    describe("cartesian", () => {
        it("has withTooltip enabled", () => {
            expect(cartesian.withTooltip).toBe(true);
        });

        it("has animation duration set", () => {
            expect(cartesian.tooltipAnimationDuration).toBe(100);
        });

        it("has stroke dash array for grid", () => {
            expect(cartesian.strokeDasharray).toBe("3 3");
        });

        it("has no tick lines", () => {
            expect(cartesian.tickLine).toBe("none");
        });

        it("uses fmtNum for value formatting", () => {
            expect(cartesian.valueFormatter).toBe(fmtNum);
        });

        it("has yAxis props with auto width", () => {
            expect(cartesian.yAxisProps.width).toBe("auto");
        });

        it("has yAxis tick margin", () => {
            expect(cartesian.yAxisProps.tickMargin).toBe(6);
        });

        it("valueFormatter works with numbers", () => {
            expect(cartesian.valueFormatter(1234)).toMatch(/1\s234/);
        });

        it("valueFormatter works with nulls", () => {
            expect(cartesian.valueFormatter(null)).toBe("");
        });
    });
});
