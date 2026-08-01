import { describe, expect, it } from "vitest";
import { mutationGateDemo } from "./mutationGateDemo.js";

describe("mutationGateDemo", () => {
    it("handles positive values", () => {
        expect(mutationGateDemo(1)).toBe(2);
    });
});
