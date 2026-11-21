import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MantineProvider } from "@mantine/core";
import { MoneyChartTooltip, TrendChartTooltip } from "./ChartTooltip.jsx";

describe("chart tooltip formatting", () => {
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

    it("labels every money series with the ruble unit", () => {
        const html = renderToStaticMarkup(
            <MantineProvider>
                <MoneyChartTooltip
                    label="Jul '26"
                    payload={[
                        {
                            name: "Expenses",
                            value: 84071,
                            color: "red",
                            payload: { Expenses: 84071 },
                        },
                    ]}
                />
            </MantineProvider>,
        );

        expect(html).toContain("Expenses");
        expect(html).toContain("84");
        expect(html).toContain("₽");
    });

    it("survives a missing payload without throwing", () => {
        const html = renderToStaticMarkup(
            <MantineProvider>
                <MoneyChartTooltip label="Jul '26" />
            </MantineProvider>,
        );

        expect(html).not.toContain("₽");
    });
});
