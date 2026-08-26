import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const themeCss = readFileSync("src/theme.css", "utf8");

const values = (name: string) =>
    Array.from(themeCss.matchAll(new RegExp(`${name}:\\s*([^;]+);`, "g")), ([, value]) =>
        value.trim(),
    );

const palette = [
    "#ef5a17",
    "#4269d0",
    "#3ca951",
    "#a463f2",
    "#ff8ab7",
    "#6cc5b0",
    "#efb118",
    "#9c6b4e",
    "#97bbf5",
    "#d94f4f",
    "#6b4fbb",
    "#9498a0",
];

describe("theme colors", () => {
    it("defines the reference palette and chart roles once", () => {
        expect(palette.map((_, index) => values(`--m-chart-${index + 1}`))).toEqual(
            palette.map((color) => [color]),
        );
        expect(values("--m-accent")).toEqual(["var(--m-chart-1)"]);
        expect(values("--m-income")).toEqual(["var(--m-chart-3)"]);
        expect(values("--m-expense")).toEqual(["var(--m-chart-10)"]);
        expect(values("--m-warning")).toEqual(["var(--m-chart-7)"]);
        expect(themeCss).not.toMatch(/--m-chart-(accent|income|expense|warning):/);
        expect(values("--g-color-text-positive")).toEqual(["var(--m-income)"]);
        expect(values("--g-color-text-danger")).toEqual(["var(--m-expense)"]);
        expect(values("--g-color-text-warning")).toEqual(["var(--m-warning)"]);
    });
});
