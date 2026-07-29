import { describe, expect, it } from "vitest";
import {
    amountInput,
    fmtDate,
    groupAmount,
    money,
    moneyCompact,
    parseRub,
    rub,
    rubExact,
} from "./format.js";

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

    it("rounds to whole rubles", () => {
        expect(rub(12345)).toBe("123");
        expect(rub(12399)).toBe("124");
    });
});

describe("rubExact", () => {
    it("keeps two fractional digits", () => {
        expect(rubExact(1234567)).toBe(`12${NB}345,67`);
        expect(rubExact(0)).toBe("0,00");
        expect(rubExact(-45050)).toBe("-450,50");
    });
});

describe("money", () => {
    it("appends the ruble sign to the rounded value", () => {
        expect(money(17679400)).toBe(`176${NB}794 ₽`);
        expect(money(0)).toBe("0 ₽");
    });
});

describe("moneyCompact", () => {
    it("abbreviates millions and thousands and keeps small amounts whole", () => {
        expect(moneyCompact(150_000_000)).toBe("1.5M");
        expect(moneyCompact(1_234_500)).toBe("12k");
        expect(moneyCompact(45000)).toBe("450");
        expect(moneyCompact(0)).toBe("0");
        expect(moneyCompact(-150_000_000)).toBe("-1.5M");
    });

    it("switches suffix exactly at the million and thousand marks", () => {
        // the boundaries are inclusive: 1M rounds to "1.0M", 1k to "1k"
        expect(moneyCompact(100_000_000)).toBe("1.0M");
        expect(moneyCompact(100_000)).toBe("1k");
    });
});

describe("parseRub", () => {
    it("parses grouped, comma and plain forms to kopecks", () => {
        expect(parseRub(`12${NB}345,50`)).toBe(1234550);
        expect(parseRub("12345.5")).toBe(1234550);
        expect(parseRub("12 345")).toBe(1234500);
    });

    it("returns 0 for empty input and null for junk", () => {
        expect(parseRub("")).toBe(0);
        expect(parseRub("   ")).toBe(0);
        expect(parseRub("abc")).toBeNull();
    });

    it("handles negatives", () => {
        expect(parseRub("-450,50")).toBe(-45050);
    });
});

describe("fmtDate", () => {
    it("turns an ISO date into DD.MM.YYYY", () => {
        expect(fmtDate("2026-03-05")).toBe("05.03.2026");
        expect(fmtDate("2026-12-31T12:00:00")).toBe("31.12.2026");
    });
});
