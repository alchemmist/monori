import { describe, expect, it } from "vitest";
import { CURRENCIES, currencyOptions, DEFAULT_CURRENCY } from "./currencies.js";

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
            expect(options[0].value).toBe("RUB");
        }
    });

    it("prepends an unknown code as its own bare option", () => {
        const options = currencyOptions("xyz");
        expect(options).toHaveLength(CURRENCIES.length + 1);
        // upper-cased before the lookup, and shown as its own value=label option
        expect(options[0]).toEqual({ value: "XYZ", label: "XYZ" });
        expect(options[1].value).toBe("RUB");
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
