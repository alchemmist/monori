import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MantineProvider } from "@mantine/core";
import { chartMoney, trendUnit } from "../pages/chartTheme.js";
import { TrendChartTooltip } from "./ChartTooltip.jsx";

const NB = "\u00a0";

describe("chart tooltip formatting", () => {
    it("formats chart values as rounded, grouped rubles", () => {
        expect(chartMoney(84070.5)).toBe(`84${NB}071${NB}₽`);
        expect(chartMoney(12345)).toBe(`12${NB}345${NB}₽`);
    });

    it("uses percent only for the savings-rate series", () => {
        expect(trendUnit("Income")).toBe(`${NB}₽`);
        expect(trendUnit("Expenses")).toBe(`${NB}₽`);
        expect(trendUnit("Savings rate %")).toBe("%");
    });

    it("omits null series instead of rendering a unit-only row", () => {
        const html = renderToStaticMarkup(
            <MantineProvider>
                <TrendChartTooltip
                    label="Jul '26"
                    payload={[
                        {
                            name: "Income",
                            value: 12345,
                            color: "green",
                            payload: { Income: 12345 },
                        },
                        {
                            name: "Savings rate %",
                            value: null,
                            color: "orange",
                            payload: { "Savings rate %": null },
                        },
                    ]}
                />
            </MantineProvider>,
        );

        expect(html).toContain("Income");
        expect(html).toContain("12 345 ₽");
        expect(html).not.toContain("Savings rate %");
    });
});
