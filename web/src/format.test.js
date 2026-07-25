import { describe, expect, it } from "vitest";
import { amountInput, groupAmount, money, parseRub, rub } from "./format.js";

const NB = "\u00a0";

describe("groupAmount", () => {
    it("groups the integer part in threes", () => {
        expect(groupAmount("176794")).toBe(`176${NB}794`);
        expect(groupAmount("1234567")).toBe(`1${NB}234${NB}567`);
        expect(groupAmount("999")).toBe("999");
    });

    it("keeps a half-typed number usable", () => {
        expect(groupAmount("")).toBe("");
        expect(groupAmount("-")).toBe("-");
        expect(groupAmount("1234,")).toBe(`1${NB}234,`);
        expect(groupAmount("-1234.5")).toBe(`-1${NB}234.5`);
    });

    it("drops junk and extra decimals", () => {
        expect(groupAmount("12a34")).toBe(`1${NB}234`);
        expect(groupAmount("12,3456")).toBe("12,34");
    });

    it("is stable when applied to its own output", () => {
        const once = groupAmount("176794,5");
        expect(groupAmount(once)).toBe(once);
    });
});

describe("amountInput", () => {
    it("renders kopecks the way a person would type them", () => {
        expect(amountInput(17679400)).toBe(`176${NB}794`);
        expect(amountInput(123456)).toBe(`1${NB}234,56`);
        expect(amountInput(0)).toBe("");
        expect(amountInput(null)).toBe("");
    });

    it("round-trips through parseRub", () => {
        for (const kop of [1, 999, 100000, 17679400, -450050]) {
            expect(parseRub(amountInput(kop))).toBe(kop);
        }
    });
});

describe("rub", () => {
    it("separates thousands", () => {
        expect(rub(17679400)).toBe(`176${NB}794`);
    });
});

describe("money", () => {
    it("labels an amount with its currency", () => {
        expect(money(17679400, "RUB")).toBe(`176${NB}794 ₽`);
        expect(money(17679400, "gel")).toBe(`176${NB}794 ₾`);
    });

    it("defaults to rubles, since a total with no currency is the base one", () => {
        expect(money(50000)).toBe("500 ₽");
    });

    it("prints an unknown code rather than dropping it", () => {
        expect(money(50000, "XYZ")).toBe("500 XYZ");
    });
});
