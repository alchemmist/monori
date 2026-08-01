import { describe, it, expect } from "vitest";
import {
    CreditCard,
    CircleRuble,
    CircleDollar,
    Wallet,
    Sack,
    Briefcase,
    House,
    ChartLine,
    Percent,
    Gift,
    Star,
    Heart,
} from "@gravity-ui/icons";
import {
    ACCOUNT_ICONS,
    ACCOUNT_COLORS,
    DEFAULT_ACCOUNT_COLOR,
    accountIcon,
} from "./accountIcons.js";

// written out by hand rather than derived from ACCOUNT_ICONS: a table built
// from the source under test can never disagree with it
const EXPECTED = [
    ["wallet", Wallet],
    ["card", CreditCard],
    ["ruble", CircleRuble],
    ["dollar", CircleDollar],
    ["sack", Sack],
    ["briefcase", Briefcase],
    ["house", House],
    ["chart", ChartLine],
    ["percent", Percent],
    ["gift", Gift],
    ["star", Star],
    ["heart", Heart],
];

describe("accountIcons", () => {
    it("maps every stored name to its own glyph", () => {
        for (const [name, Icon] of EXPECTED as Array<[string, (typeof EXPECTED)[number][1]]>) {
            expect(accountIcon(name)).toBe(Icon);
        }
    });

    it("lists exactly the mapped names, in order and without duplicates", () => {
        expect(ACCOUNT_ICONS.map((i) => i.name)).toEqual(EXPECTED.map(([name]) => name));
    });

    it("falls back to the wallet for names it does not know", () => {
        for (const name of ["unknown_icon", "WALLET", "", null, undefined]) {
            expect(accountIcon(name)).toBe(Wallet);
        }
    });

    it("defaults to the first preset color and keeps the presets distinct hex values", () => {
        expect(DEFAULT_ACCOUNT_COLOR).toBe("#5b6472");
        expect(ACCOUNT_COLORS[0]).toBe(DEFAULT_ACCOUNT_COLOR);
        expect(new Set(ACCOUNT_COLORS).size).toBe(ACCOUNT_COLORS.length);
        for (const color of ACCOUNT_COLORS) {
            expect(color).toMatch(/^#[0-9a-f]{6}$/i);
        }
    });
});
