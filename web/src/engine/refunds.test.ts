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
});
