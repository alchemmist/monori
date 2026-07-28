import { describe, expect, it } from "vitest";
import { signedSplitAmount } from "./splitAmounts.js";

describe("signedSplitAmount", () => {
    it("derives the sign from an expense transaction", () => {
        expect(signedSplitAmount(500, -1_000)).toBe(-500);
        expect(signedSplitAmount(-500, -1_000)).toBe(-500);
    });

    it("derives the sign from an income transaction", () => {
        expect(signedSplitAmount(500, 1_000)).toBe(500);
        expect(signedSplitAmount(-500, 1_000)).toBe(500);
    });

    it("collapses to zero for a zero-amount transaction", () => {
        // Math.sign(0) is 0, so the magnitude drops out entirely — this is the
        // one input where multiplying and dividing by the sign disagree
        expect(signedSplitAmount(500, 0)).toBe(0);
    });
});
