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
});
