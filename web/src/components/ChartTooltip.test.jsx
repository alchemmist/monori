import { describe, expect, it } from "vitest";
import { chartMoney, trendUnit } from "../pages/chartTheme.js";

const NB = "\u00a0";

describe("chart tooltip formatting", () => {
    it("formats chart values as rounded, grouped rubles", () => {
        expect(chartMoney(84070.5)).toBe(`84${NB}071${NB}₽`);
        expect(chartMoney(12345)).toBe(`12${NB}345${NB}₽`);
    });

    it("uses percent only for the savings-rate series", () => {
        expect(trendUnit("Income")).toBe(`${NB}₽`);
        expect(trendUnit("Expenses")).toBe(`${NB}₽`);
        expect(trendUnit("Savings rate %")).toBe("%");
    });
});
