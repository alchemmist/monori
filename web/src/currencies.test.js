import { describe, expect, it } from "vitest";
import {
    CURRENCIES,
    currencyName,
    currencyOptions,
    currencySymbol,
    normalizeCurrency,
} from "./currencies.js";

describe("normalizeCurrency", () => {
    it("trims and upper-cases", () => {
        expect(normalizeCurrency(" gel ")).toBe("GEL");
    });

    it("falls back when there is nothing to normalize", () => {
        expect(normalizeCurrency(null)).toBe("RUB");
        expect(normalizeCurrency("")).toBe("RUB");
        expect(normalizeCurrency(undefined, "USD")).toBe("USD");
        expect(normalizeCurrency("", "")).toBe("");
    });

    it("leaves an unknown code alone", () => {
        // data can outlive the registry; reading it back must not rewrite it
        expect(normalizeCurrency("xyz")).toBe("XYZ");
    });
});

describe("currencySymbol", () => {
    it("knows the registry", () => {
        expect(currencySymbol("RUB")).toBe("₽");
        expect(currencySymbol("gel")).toBe("₾");
        expect(currencyName("GEL")).toBe("Georgian lari");
    });

    it("prints an unknown code as itself", () => {
        expect(currencySymbol("XYZ")).toBe("XYZ");
        expect(currencySymbol("")).toBe("");
    });
});

describe("currencyOptions", () => {
    it("offers every currency", () => {
        expect(currencyOptions().map((o) => o.value)).toEqual(CURRENCIES.map((c) => c.code));
    });

    it("keeps the current value selectable even when it is off the list", () => {
        const options = currencyOptions("xyz");
        expect(options[0]).toEqual({ value: "XYZ", label: "XYZ" });
        expect(options).toHaveLength(CURRENCIES.length + 1);
    });

    it("does not duplicate a code that is already on the list", () => {
        expect(currencyOptions("usd")).toHaveLength(CURRENCIES.length);
    });
});

describe("the registry itself", () => {
    it("has no duplicate codes", () => {
        expect(new Set(CURRENCIES.map((c) => c.code)).size).toBe(CURRENCIES.length);
    });

    it("gives every currency a symbol", () => {
        expect(CURRENCIES.every((c) => c.symbol && c.name)).toBe(true);
    });
});
