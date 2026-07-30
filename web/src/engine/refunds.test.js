import { describe, expect, it } from "vitest";
import { refundMerchantKey } from "./refunds.js";

describe("refundMerchantKey", () => {
    it("matches refund descriptions to the original merchant", () => {
        expect(refundMerchantKey("Lenta 123 RETURN")).toBe(refundMerchantKey("Lenta 456"));
        expect(refundMerchantKey("Магазин Возврат 24")).toBe(refundMerchantKey("Магазин 1000"));
    });
});
