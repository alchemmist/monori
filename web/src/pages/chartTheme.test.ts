import { describe, expect, it } from "vitest";
import { PALETTE, fmtNum } from "./chartTheme.js";

describe("chartTheme", () => {
    describe("PALETTE", () => {
        it("is a set of distinct hex colors", () => {
            expect(PALETTE).toHaveLength(12);
            for (const color of PALETTE) expect(color).toMatch(/^#[0-9a-f]{6}$/i);
            expect(new Set(PALETTE).size).toBe(PALETTE.length);
        });

        it("leads with the brand orange so the first series carries the accent", () => {
            expect(PALETTE[0]).toBe("#ef5a17");
        });
    });

    describe("fmtNum", () => {
        it("renders nothing for a missing value", () => {
            expect(fmtNum(null)).toBe("");
            expect(fmtNum(undefined)).toBe("");
        });

        it("groups thousands with the ru-RU space separator", () => {
            expect(fmtNum(1000)).toMatch(/^1\s000$/);
            expect(fmtNum(1234567)).toMatch(/^1\s234\s567$/);
        });

        it("rounds to whole units", () => {
            expect(fmtNum(1234.5)).toMatch(/^1\s235$/);
            expect(fmtNum(1234.4)).toMatch(/^1\s234$/);
        });

        it("keeps the sign on negatives and formats zero plainly", () => {
            expect(fmtNum(-1234)).toMatch(/^-1\s234$/);
            expect(fmtNum(0)).toBe("0");
        });
    });
});
