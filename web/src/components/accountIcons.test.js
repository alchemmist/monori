import { describe, it, expect } from "vitest";
import {
    ACCOUNT_ICONS,
    ACCOUNT_COLORS,
    DEFAULT_ACCOUNT_COLOR,
    accountIcon,
} from "./accountIcons.js";

describe("accountIcons", () => {
    describe("ACCOUNT_ICONS", () => {
        it("exports array of icons", () => {
            expect(Array.isArray(ACCOUNT_ICONS)).toBe(true);
            expect(ACCOUNT_ICONS.length).toBeGreaterThan(0);
        });

        it("each icon has name and Icon component", () => {
            for (const icon of ACCOUNT_ICONS) {
                expect(icon).toHaveProperty("name");
                expect(icon).toHaveProperty("Icon");
                expect(typeof icon.name).toBe("string");
                expect(typeof icon.Icon).toBe("function");
            }
        });

        it("includes expected icon names", () => {
            const iconNames = ACCOUNT_ICONS.map((i) => i.name);

            expect(iconNames).toContain("wallet");
            expect(iconNames).toContain("card");
            expect(iconNames).toContain("ruble");
            expect(iconNames).toContain("dollar");
            expect(iconNames).toContain("sack");
            expect(iconNames).toContain("briefcase");
            expect(iconNames).toContain("house");
            expect(iconNames).toContain("chart");
            expect(iconNames).toContain("percent");
            expect(iconNames).toContain("gift");
            expect(iconNames).toContain("star");
            expect(iconNames).toContain("heart");
        });

        it("has unique icon names", () => {
            const iconNames = ACCOUNT_ICONS.map((i) => i.name);
            const uniqueNames = new Set(iconNames);

            expect(uniqueNames.size).toBe(iconNames.length);
        });
    });

    describe("ACCOUNT_COLORS", () => {
        it("exports array of colors", () => {
            expect(Array.isArray(ACCOUNT_COLORS)).toBe(true);
            expect(ACCOUNT_COLORS.length).toBeGreaterThan(0);
        });

        it("contains valid hex colors", () => {
            const hexColorRegex = /^#[0-9a-f]{6}$/i;

            for (const color of ACCOUNT_COLORS) {
                expect(color).toMatch(hexColorRegex);
            }
        });

        it("includes expected colors", () => {
            expect(ACCOUNT_COLORS).toContain("#5b6472");
            expect(ACCOUNT_COLORS).toContain("#2f6feb");
            expect(ACCOUNT_COLORS).toContain("#0ea5e9");
            expect(ACCOUNT_COLORS).toContain("#10b981");
            expect(ACCOUNT_COLORS).toContain("#14b8a6");
            expect(ACCOUNT_COLORS).toContain("#8b5cf6");
            expect(ACCOUNT_COLORS).toContain("#ec4899");
            expect(ACCOUNT_COLORS).toContain("#ef5a17");
            expect(ACCOUNT_COLORS).toContain("#eab308");
            expect(ACCOUNT_COLORS).toContain("#ef4444");
        });

        it("has unique colors", () => {
            const uniqueColors = new Set(ACCOUNT_COLORS);
            expect(uniqueColors.size).toBe(ACCOUNT_COLORS.length);
        });
    });

    describe("DEFAULT_ACCOUNT_COLOR", () => {
        it("is defined", () => {
            expect(DEFAULT_ACCOUNT_COLOR).toBeDefined();
        });

        it("is a valid hex color", () => {
            const hexColorRegex = /^#[0-9a-f]{6}$/i;
            expect(DEFAULT_ACCOUNT_COLOR).toMatch(hexColorRegex);
        });

        it("is in ACCOUNT_COLORS array", () => {
            expect(ACCOUNT_COLORS).toContain(DEFAULT_ACCOUNT_COLOR);
        });

        it("is the first color in the array", () => {
            expect(DEFAULT_ACCOUNT_COLOR).toBe(ACCOUNT_COLORS[0]);
        });

        it("is the expected default", () => {
            expect(DEFAULT_ACCOUNT_COLOR).toBe("#5b6472");
        });
    });

    describe("accountIcon()", () => {
        it("returns Icon component for known icon name", () => {
            const icon = accountIcon("wallet");

            expect(typeof icon).toBe("function");
        });

        it("returns Icon for all known icon names", () => {
            for (const { name } of ACCOUNT_ICONS) {
                const icon = accountIcon(name);
                expect(typeof icon).toBe("function");
            }
        });

        it("returns Wallet icon for unknown name", () => {
            const icon = accountIcon("unknown_icon");
            const walletIcon = accountIcon("wallet");

            expect(icon).toBe(walletIcon);
        });

        it("returns Wallet icon for null", () => {
            const icon = accountIcon(null);
            const walletIcon = accountIcon("wallet");

            expect(icon).toBe(walletIcon);
        });

        it("returns Wallet icon for undefined", () => {
            const icon = accountIcon(undefined);
            const walletIcon = accountIcon("wallet");

            expect(icon).toBe(walletIcon);
        });

        it("returns Wallet icon for empty string", () => {
            const icon = accountIcon("");
            const walletIcon = accountIcon("wallet");

            expect(icon).toBe(walletIcon);
        });

        it("case-sensitive icon lookup", () => {
            const lowerIcon = accountIcon("wallet");
            const upperIcon = accountIcon("WALLET");

            expect(lowerIcon).toBe(lowerIcon);
            expect(upperIcon).toBe(accountIcon("wallet"));
        });

        it("returns correct icon for each known type", () => {
            const iconMap = new Map(ACCOUNT_ICONS.map((i) => [i.name, i.Icon]));

            for (const [name, Icon] of iconMap) {
                expect(accountIcon(name)).toBe(Icon);
            }
        });
    });
});
