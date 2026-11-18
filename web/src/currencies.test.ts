import { describe, expect, it } from "vitest";
import {
    CURRENCIES,
    currencyOptions,
    DEFAULT_CURRENCY,
    currencyName,
    currencySymbol,
    normalizeCurrency,
} from "./currencies.js";

describe("currencyOptions", () => {
    it("offers one labelled option per known currency", () => {
        const options = currencyOptions(null);
        expect(options).toHaveLength(CURRENCIES.length);
        expect(options[0]).toEqual({ value: "RUB", label: "RUB · Russian ruble" });
        expect(options.map((o) => o.value)).toEqual(CURRENCIES.map((c) => c.code));
    });

    it("does not prepend anything for a known code, whatever its case or padding", () => {
        for (const current of ["RUB", "usd", " eur ", "Gbp"]) {
            const options = currencyOptions(current);
            expect(options).toHaveLength(CURRENCIES.length);
            // the known code keeps its canonical position, it is not hoisted
            expect(options[0]!.value).toBe("RUB");
        }
    });

    it("prepends an unknown code as its own bare option", () => {
        const options = currencyOptions("xyz");
        expect(options).toHaveLength(CURRENCIES.length + 1);
        // upper-cased before the lookup, and shown as its own value=label option
        expect(options[0]).toEqual({ value: "XYZ", label: "XYZ" });
        expect(options[1]!.value).toBe("RUB");
    });

    it("adds no option for an empty, blank or missing current value", () => {
        for (const current of ["", "   ", null, undefined]) {
            expect(currencyOptions(current)).toHaveLength(CURRENCIES.length);
        }
    });

    it("defaults to the ruble", () => {
        expect(DEFAULT_CURRENCY).toBe("RUB");
        expect(CURRENCIES.some((c) => c.code === DEFAULT_CURRENCY)).toBe(true);
    });
});

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
