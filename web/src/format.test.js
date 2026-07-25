import { describe, expect, it } from "vitest";
import {
    rub,
    rubExact,
    money,
    moneyCompact,
    parseRub,
    fmtDate,
    MONTHS,
    MONTHS_SHORT,
} from "./format.js";

describe("format", () => {
    describe("rub", () => {
        it("converts kopecks to rounded rubles with formatting", () => {
            expect(rub(123456)).toMatch(/1\s235/);
        });

        it("rounds correctly from kopecks", () => {
            expect(rub(15049)).toBe("150");
            expect(rub(15050)).toBe("151");
        });

        it("handles zero", () => {
            expect(rub(0)).toBe("0");
        });

        it("formats negative amounts", () => {
            expect(rub(-500000)).toMatch(/-5\s000/);
        });

        it("uses Russian locale formatting with space as thousands separator", () => {
            expect(rub(1234567890)).toMatch(/12\s345\s679/);
        });

        it("rounds down for amounts less than 50 kopecks", () => {
            expect(rub(1049)).toBe("10");
        });

        it("rounds up for amounts 50 kopecks or more", () => {
            expect(rub(1050)).toBe("11");
        });
    });

    describe("rubExact", () => {
        it("converts kopecks to rubles with two decimal places", () => {
            expect(rubExact(123456)).toMatch(/1\s234,56/);
        });

        it("handles zero", () => {
            expect(rubExact(0)).toBe("0,00");
        });

        it("formats negative amounts", () => {
            expect(rubExact(-123456)).toMatch(/-1\s234,56/);
        });

        it("always shows two decimals", () => {
            expect(rubExact(100000)).toMatch(/1\s000,00/);
        });

        it("preserves fractional kopecks", () => {
            expect(rubExact(1)).toBe("0,01");
            expect(rubExact(123)).toBe("1,23");
        });
    });

    describe("money", () => {
        it("returns rub formatted value with ruble sign", () => {
            expect(money(123456)).toMatch(/1\s235\s₽/);
        });

        it("handles negative values", () => {
            expect(money(-500000)).toMatch(/-5\s000\s₽/);
        });

        it("handles zero", () => {
            expect(money(0)).toMatch(/0\s₽/);
        });

        it("includes space before ruble sign", () => {
            expect(money(100000)).toMatch(/1\s000\s₽/);
        });

        it("handles large values", () => {
            expect(money(1234567890)).toMatch(/12\s345\s679\s₽/);
        });
    });

    describe("moneyCompact", () => {
        it("formats millions with M suffix", () => {
            expect(moneyCompact(1500000000)).toBe("15.0M");
            expect(moneyCompact(2340000000)).toBe("23.4M");
        });

        it("formats thousands with k suffix", () => {
            expect(moneyCompact(1234500)).toBe("12k");
            expect(moneyCompact(5678900)).toBe("57k");
        });

        it("formats small amounts without suffix", () => {
            expect(moneyCompact(50000)).toBe("500");
            expect(moneyCompact(99900)).toBe("999");
        });

        // both cut-offs are inclusive: exactly 1k is "1k", exactly 1M is "1.0M"
        it("switches suffix at the boundary itself, not one unit past it", () => {
            expect(moneyCompact(99_999_999)).toBe("1000k");
            expect(moneyCompact(100_000_000)).toBe("1.0M");
            expect(moneyCompact(99_900)).toBe("999");
            expect(moneyCompact(100_000)).toBe("1k");
        });

        it("switches suffix at the negative boundary too", () => {
            expect(moneyCompact(-100_000_000)).toBe("-1.0M");
            expect(moneyCompact(-100_000)).toBe("-1k");
        });

        it("handles zero", () => {
            expect(moneyCompact(0)).toBe("0");
        });

        it("handles negative millions", () => {
            expect(moneyCompact(-1500000000)).toBe("-15.0M");
        });

        it("handles negative thousands", () => {
            expect(moneyCompact(-1234500)).toBe("-12k");
        });

        it("handles negative small amounts", () => {
            expect(moneyCompact(-50000)).toBe("-500");
        });

        it("uses absolute value for formatting decisions on negatives", () => {
            expect(moneyCompact(-1234500)).toBe("-12k");
        });
    });

    describe("parseRub", () => {
        it("parses integer rubles to kopecks", () => {
            expect(parseRub("100")).toBe(10000);
        });

        it("parses decimal with comma (Russian format)", () => {
            expect(parseRub("100,50")).toBe(10050);
        });

        it("parses decimal with dot", () => {
            expect(parseRub("100.50")).toBe(10050);
        });

        it("ignores spaces in input", () => {
            expect(parseRub("1 000")).toBe(100000);
            expect(parseRub("1 000,50")).toBe(100050);
        });

        it("handles whitespace trimming", () => {
            expect(parseRub("  100  ")).toBe(10000);
        });

        it("returns zero for empty string", () => {
            expect(parseRub("")).toBe(0);
        });

        it("returns zero for whitespace-only string", () => {
            expect(parseRub("   ")).toBe(0);
        });

        it("returns null for invalid input", () => {
            expect(parseRub("abc")).toBe(null);
            expect(parseRub("12.34.56")).toBe(null);
        });

        it("handles negative values", () => {
            expect(parseRub("-100")).toBe(-10000);
            expect(parseRub("-100,50")).toBe(-10050);
        });

        it("handles very small fractions", () => {
            expect(parseRub("0.01")).toBe(1);
        });

        it("rounds fractional kopecks", () => {
            expect(parseRub("100.005")).toBe(10001);
        });

        it("accepts Number as input", () => {
            expect(parseRub(100)).toBe(10000);
            expect(parseRub(100.5)).toBe(10050);
        });
    });

    describe("fmtDate", () => {
        it("formats ISO date to DD.MM.YYYY", () => {
            expect(fmtDate("2026-07-25")).toBe("25.07.2026");
        });

        it("handles dates with leading zeros", () => {
            expect(fmtDate("2026-01-05")).toBe("05.01.2026");
        });

        it("handles year boundaries", () => {
            expect(fmtDate("2025-12-31")).toBe("31.12.2025");
        });

        it("handles leap year dates", () => {
            expect(fmtDate("2024-02-29")).toBe("29.02.2024");
        });

        it("ignores time portion of ISO string", () => {
            expect(fmtDate("2026-07-25T14:30:00")).toBe("25.07.2026");
        });
    });

    describe("MONTHS and MONTHS_SHORT", () => {
        it("exports the full month names in calendar order", () => {
            expect(MONTHS).toEqual([
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]);
        });

        it("exports the three-letter abbreviations in calendar order", () => {
            expect(MONTHS_SHORT).toEqual([
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ]);
        });
    });
});
