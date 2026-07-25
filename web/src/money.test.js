import { describe, expect, it } from "vitest";
import { convertAmount, isMixedCurrency, ratesByCode, totalInBase } from "./money.js";

const RATES = [
    { code: "RUB", rate: 1 },
    { code: "GEL", rate: 30 },
    { code: "USD", rate: 90 },
];

describe("ratesByCode", () => {
    it("always quotes the pivot as one, even if the server left it out", () => {
        expect(ratesByCode([{ code: "GEL", rate: 30 }]).get("RUB")).toBe(1);
    });
});

describe("convertAmount", () => {
    it("is an exact identity within one currency", () => {
        expect(convertAmount(7, "USD", "usd", RATES)).toBe(7);
        expect(convertAmount(-12345, "GEL", "GEL", RATES)).toBe(-12345);
    });

    it("goes through the pivot", () => {
        // 100.00 GEL = 3000 RUB = 33.33 USD
        expect(convertAmount(10000, "GEL", "RUB", RATES)).toBe(300000);
        expect(convertAmount(300000, "RUB", "GEL", RATES)).toBe(10000);
        expect(convertAmount(10000, "GEL", "USD", RATES)).toBe(3333);
    });

    it("keeps the sign", () => {
        expect(convertAmount(-10000, "GEL", "RUB", RATES)).toBe(-300000);
    });

    it("carries an unquoted currency across at face value", () => {
        // the alternative is dropping the money out of the total silently
        expect(convertAmount(500, "XYZ", "RUB", RATES)).toBe(500);
    });

    it("accepts a prepared lookup as well as the raw list", () => {
        expect(convertAmount(10000, "GEL", "RUB", ratesByCode(RATES))).toBe(300000);
    });
});

const ACCOUNTS = [
    { id: 1, currency: "RUB", archived: false },
    { id: 2, currency: "GEL", archived: false },
    { id: 3, currency: "USD", archived: true },
];
const BALANCES = new Map([
    [1, 100000],
    [2, 10000],
    [3, 999999],
]);

describe("totalInBase", () => {
    it("converts each account before adding it", () => {
        // 1000.00 RUB + 100.00 GEL at 30 = 1000 + 3000 rubles
        expect(totalInBase(ACCOUNTS, BALANCES, "RUB", RATES)).toBe(400000);
    });

    it("leaves archived accounts out, as the page does", () => {
        expect(totalInBase(ACCOUNTS, BALANCES, "RUB", RATES)).toBeLessThan(999999);
    });

    it("reports in whichever currency it is asked for", () => {
        // the same money, said in lari
        expect(totalInBase(ACCOUNTS, BALANCES, "GEL", RATES)).toBe(13333);
    });

    it("treats a missing balance as zero", () => {
        expect(totalInBase(ACCOUNTS, new Map(), "RUB", RATES)).toBe(0);
    });
});

describe("isMixedCurrency", () => {
    it("is true only when an active account is held in something else", () => {
        expect(isMixedCurrency(ACCOUNTS, "RUB")).toBe(true);
        expect(isMixedCurrency([ACCOUNTS[0]], "RUB")).toBe(false);
        // the odd one out is archived, so there is nothing left to reconcile
        expect(isMixedCurrency([ACCOUNTS[0], ACCOUNTS[2]], "RUB")).toBe(false);
    });
});
