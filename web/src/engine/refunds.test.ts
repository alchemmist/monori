import { describe, expect, it } from "vitest";
import { refundMerchantKey } from "./refunds.js";

describe("refundMerchantKey", () => {
    it.each([
        ["Shop REFUND", "shop"],
        ["возврат Shop 123", "shop"],
        ["RETURN100 Shop", "shop"],
        ["Shop return456", "shop"],
    ])("normalizes %s", (value, expected) => {
        expect(refundMerchantKey(value)).toBe(expected);
    });

    it("returns an empty key when no merchant letters remain", () => {
        expect(refundMerchantKey("123 REFUND 456")).toBe("");
    });
});
