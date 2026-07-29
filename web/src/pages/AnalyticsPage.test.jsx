import { beforeEach, describe, expect, it, vi } from "vitest";

// Real charts render an SVG whose numbers are unreadable from a test; each one
// is swapped for a node carrying the exact rows the page computed, so the
// plan-vs-fact colors and the yearly series are assertable.
vi.mock("@mantine/charts", () => {
    const serialize = (testid) =>
        function Chart({ data, series }) {
            return (
                <div
                    data-testid={testid}
                    data-series={JSON.stringify(data)}
                    data-chart-series={JSON.stringify(series)}
                />
            );
        };
    return { BarChart: serialize("bar-chart"), LineChart: serialize("line-chart") };
});

import AnalyticsPage from "./AnalyticsPage.jsx";
import { renderUI, resetStore, screen, seed } from "../test/render.jsx";
import { computeRange } from "../engine/budget.js";
import { SERIES } from "./chartTheme.js";

const FIRST_YEAR = 2020;
const now = new Date();
const YEAR = now.getFullYear();
const PREV = YEAR - 1;

/** Rows a mocked chart was handed, parsed back out of its `data-series`. */
function series(testid, index = 0) {
    return JSON.parse(screen.getAllByTestId(testid)[index].dataset.series);
}

function chartSeries(title) {
    const card = screen.getByText(new RegExp(title)).closest(".chart-card");
    return JSON.parse(card.querySelector('[data-testid="bar-chart"]').dataset.series);
}

function chartSeriesConfig(title) {
    const card = screen.getByText(new RegExp(title)).closest(".chart-card");
    return JSON.parse(card.querySelector('[data-testid="bar-chart"]').dataset.chartSeries);
}

// ru-RU groups thousands with a non-breaking space. Expected strings below are
// written with plain spaces throughout and only the digit groups swapped, so
// they stay readable while matching the rendered text exactly.
const n = (s) => s.replace(/(\d) (?=\d)/g, "$1\u00a0");

const kpi = (label) =>
    screen
        .getAllByText(label)
        .map((el) => el.closest(".kpi"))
        .find(Boolean);
const kpiValue = (label) => kpi(label).querySelector(".kpi__value").textContent;

const txn = (id, patch) => ({
    id,
    accountId: 1,
    categoryId: 2,
    amount: -1000,
    date: `${YEAR}-01-10`,
    description: "shop",
    transferId: null,
    ...patch,
});

/**
 * Hand-built year: 300 000 ₽ in, 100 000 ₽ out, so every derived figure is
 * knowable — net 200 000, savings rate 66.67% → "67%", avg/mo 100 000.
 */
function seedKnownYear(patch = {}) {
    return seed({
        transactions: [
            txn(1, { categoryId: 1, amount: 300_000_00, date: `${YEAR}-01-15` }),
            txn(2, { categoryId: 2, amount: -60_000_00, date: `${YEAR}-01-20` }),
            txn(3, { categoryId: 3, amount: -40_000_00, date: `${YEAR}-01-25` }),
        ],
        ...patch,
    });
}

function render(snapshot, { lastYear = YEAR } = {}) {
    const results = computeRange(snapshot, FIRST_YEAR, Math.max(lastYear, YEAR));
    return renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={lastYear} />);
}

describe("AnalyticsPage", () => {
    beforeEach(() => {
        resetStore();
    });

    describe("year totals", () => {
        it("sums the selected year's income, expenses, net and savings rate", () => {
            render(seedKnownYear());

            expect(kpiValue("Income")).toBe(n("300 000 ₽"));
            expect(kpiValue("Expenses")).toBe(n("100 000 ₽"));
            expect(kpiValue("Net saved")).toBe(n("200 000 ₽"));
            expect(kpiValue("Savings rate")).toBe("67%");
        });

        it("repeats those totals in the all-time report table, one row per year", () => {
            render(
                seed({
                    transactions: [
                        txn(1, { categoryId: 1, amount: 300_000_00, date: `${YEAR}-01-15` }),
                        txn(2, { categoryId: 2, amount: -100_000_00, date: `${YEAR}-01-20` }),
                        txn(3, { categoryId: 1, amount: 100_000_00, date: `${PREV}-03-15` }),
                        txn(4, { categoryId: 2, amount: -150_000_00, date: `${PREV}-04-20` }),
                    ],
                }),
            );

            const cells = (year) =>
                [
                    ...[...document.querySelectorAll(".report-table tbody tr")]
                        .find((tr) => tr.firstChild.textContent === year)
                        .querySelectorAll("td"),
                ].map((td) => td.textContent);
            // year, income, expenses, net, rate, avg/mo (2 months of data in PREV)
            expect(cells(String(PREV))).toEqual(
                [String(PREV), "100 000", "150 000", "-50 000", "-50%", "75 000"].map(n),
            );
            expect(cells(String(YEAR))).toEqual(
                [String(YEAR), "300 000", "100 000", "200 000", "67%", "100 000"].map(n),
            );
        });

        it("marks the selected year's row as current", () => {
            const { container } = render(seedKnownYear());

            const current = container.querySelectorAll(".report-table__row_current");
            expect(current).toHaveLength(1);
            expect(current[0]).toHaveTextContent(String(YEAR));
        });
    });

    describe("year selector", () => {
        it("offers every year up to today and never a future one", async () => {
            const { user } = render(seedKnownYear(), { lastYear: YEAR + 4 });

            await user.click(screen.getByRole("button", { name: String(YEAR) }));

            const offered = [...document.querySelectorAll('[role="option"]')].map(
                (o) => o.textContent,
            );
            expect(offered).toEqual(
                Array.from({ length: YEAR - FIRST_YEAR + 1 }, (_, i) => String(FIRST_YEAR + i)),
            );
            expect(offered).not.toContain(String(YEAR + 1));
        });

        it("recomputes the KPIs for the year the user picks", async () => {
            const { user } = render(
                seed({
                    transactions: [
                        txn(1, { categoryId: 1, amount: 300_000_00, date: `${YEAR}-01-15` }),
                        txn(2, { categoryId: 1, amount: 80_000_00, date: `${PREV}-01-15` }),
                        txn(3, { categoryId: 2, amount: -20_000_00, date: `${PREV}-02-15` }),
                    ],
                }),
            );

            expect(kpiValue("Income")).toBe(n("300 000 ₽"));

            await user.click(screen.getByRole("button", { name: String(YEAR) }));
            await user.click(document.querySelector(`[role="option"][value="${PREV}"]`));

            expect(kpiValue("Income")).toBe(n("80 000 ₽"));
            expect(kpiValue("Net saved")).toBe(n("60 000 ₽"));
            expect(screen.getByText(`Plan vs fact · ${PREV}`)).toBeInTheDocument();
        });
    });

    describe("category charts", () => {
        it("uses category names as the chart series and legend labels", () => {
            render(seedKnownYear());

            const config = chartSeriesConfig("Categories through the year");
            expect(config.map((item) => item.name)).toEqual(["Groceries", "Rent"]);
            expect(config.map((item) => item.label)).toEqual(["Groceries", "Rent"]);

            const january = chartSeries("Categories through the year")[0];
            expect(january).toMatchObject({ Groceries: 60_000, Rent: 40_000 });
            expect(january).not.toHaveProperty("cat-2");
        });
    });

    describe("plan vs fact", () => {
        it("colors a month red only once spending overshoots its budget", () => {
            render(
                seed({
                    budgets: [
                        { categoryId: 2, year: YEAR, month: 1, amount: 50_000_00 },
                        { categoryId: 2, year: YEAR, month: 2, amount: 50_000_00 },
                    ],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -90_000_00, date: `${YEAR}-01-10` }),
                        txn(2, { categoryId: 2, amount: -10_000_00, date: `${YEAR}-02-10` }),
                    ],
                }),
            );

            const [jan, feb] = series("bar-chart");
            expect(jan).toEqual({
                month: "Jan",
                Budgeted: 50_000,
                Spent: 90_000,
                spentColor: SERIES.expense,
            });
            expect(feb).toEqual({
                month: "Feb",
                Budgeted: 50_000,
                Spent: 10_000,
                spentColor: SERIES.accent,
            });
        });
    });

    describe("budget discipline grid", () => {
        const disciplineSeed = () =>
            seed({
                budgets: [
                    { categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 },
                    { categoryId: 3, year: YEAR, month: 1, amount: 10_000_00 },
                ],
                transactions: [
                    // Groceries: 11 000 of a 10 000 envelope — 110%, amber
                    txn(1, { categoryId: 2, amount: -11_000_00, date: `${YEAR}-01-10` }),
                    // Rent: 30 000 of a 10 000 envelope — 300%, red
                    txn(2, { categoryId: 3, amount: -30_000_00, date: `${YEAR}-01-11` }),
                ],
            });

        const januaryCell = (categoryName) =>
            screen
                .getByText(categoryName)
                .closest("tr")
                .querySelectorAll("td")[1]
                .querySelector(".disc-cell");

        it("paints a mild overrun amber and a heavy one red", () => {
            render(disciplineSeed());

            expect(januaryCell("Groceries")).toHaveClass("disc-cell_warn");
            expect(januaryCell("Rent")).toHaveClass("disc-cell_over");
        });

        it("spells the envelope out in each cell's tooltip", () => {
            render(disciplineSeed());

            expect(januaryCell("Groceries")).toHaveAttribute(
                "title",
                n("Groceries · Jan: 11 000 / 10 000 ₽ (110%)"),
            );
        });

        it("reports the hit rate and the worst overrun across envelopes", () => {
            render(disciplineSeed());

            // both January envelopes were blown: 0 of 2 months within budget
            expect(kpiValue("Budget hit rate")).toBe("0%");
            // 1 000 over on Groceries + 20 000 over on Rent
            expect(kpiValue("Over budget")).toBe(n("21 000 ₽"));
            expect(kpi("Over budget")).toHaveTextContent("worst: Rent");
        });

        it("says so when the year has no budgeted envelopes at all", () => {
            // spend lands in a past year, so this year's envelopes are all untouched
            render(
                seed({
                    budgets: [],
                    transactions: [txn(1, { amount: -5_000_00, date: `${PREV}-01-10` })],
                }),
            );

            expect(screen.getByText(`No budgeted envelopes in ${YEAR}`)).toBeInTheDocument();
            expect(kpiValue("Budget hit rate")).toBe("—");
        });
    });

    describe("spending patterns", () => {
        it("shares the year's spending across weekdays", () => {
            // first Monday and the Saturday five days later, whatever the year
            const firstMonday = 1 + ((8 - new Date(YEAR, 0, 1).getDay()) % 7);
            const day = (n) => String(n).padStart(2, "0");
            render(
                seed({
                    transactions: [
                        txn(1, { amount: -75_00, date: `${YEAR}-01-${day(firstMonday)}` }),
                        txn(2, { amount: -25_00, date: `${YEAR}-01-${day(firstMonday + 5)}` }),
                    ],
                }),
            );

            const weekday = chartSeries("Spending by weekday");
            expect(weekday.find((r) => r.day === "Mon").Share).toBe(75);
            expect(weekday.find((r) => r.day === "Sat").Share).toBe(25);
            expect(weekday.filter((r) => r.Share > 0)).toHaveLength(2);
        });

        it("buckets the year's spending by day of month", () => {
            render(
                seed({
                    transactions: [
                        txn(1, { amount: -300_00, date: `${YEAR}-01-03` }),
                        txn(2, { amount: -200_00, date: `${YEAR}-02-03` }),
                        txn(3, { amount: -50_00, date: `${YEAR}-02-17` }),
                    ],
                }),
            );

            const dom = chartSeries("Spending by day of month");
            expect(dom).toHaveLength(31);
            expect(dom.find((r) => r.day === "3").Spent).toBe(500);
            expect(dom.find((r) => r.day === "17").Spent).toBe(50);
        });

        it("ranks merchants by spend and folds their variants together", () => {
            render(
                seed({
                    transactions: [
                        txn(1, { amount: -100_00, date: `${YEAR}-01-03`, description: "ozon 12" }),
                        txn(2, { amount: -300_00, date: `${YEAR}-02-03`, description: "OZON *99" }),
                        txn(3, {
                            amount: -250_00,
                            date: `${YEAR}-02-04`,
                            description: "Perekrestok",
                        }),
                    ],
                }),
            );

            // merchantKey upper-cases and strips digits, so the two OZON rows fold
            expect(chartSeries("Top merchants")).toEqual([
                { name: "OZON", Spent: 400 },
                { name: "PEREKRESTOK", Spent: 250 },
            ]);
        });

        it("says so when the year has no categorized expenses", () => {
            render(seed({ transactions: [] }));

            expect(screen.getAllByText(`No categorized expenses in ${YEAR}`)).toHaveLength(2);
        });
    });

    describe("transaction stats", () => {
        it("counts expense rows and reports the median and the largest", () => {
            render(
                seed({
                    transactions: [
                        txn(1, { amount: -100_00, date: `${YEAR}-01-03` }),
                        txn(2, { amount: -500_00, date: `${YEAR}-02-03`, description: "Fridge" }),
                        txn(3, { amount: -300_00, date: `${YEAR}-03-03` }),
                        txn(4, { categoryId: 1, amount: 900_00, date: `${YEAR}-04-03` }),
                    ],
                }),
            );

            const stats = screen.getByText(/Transaction stats/).closest(".chart-card");
            const rows = [...stats.querySelectorAll(".stat-list__row")].map((r) => r.textContent);
            expect(rows[0]).toContain("Expense transactions3");
            expect(rows[1]).toContain("Median expense300 ₽");
            expect(rows[2]).toContain("Per month0"); // 3 / 12 rounds to 0
            expect(rows[3]).toContain("Largest expense");
            expect(rows[3]).toContain(`Fridge · 03.02.${YEAR}`);
            expect(rows[3]).toContain("500 ₽");
        });
    });

    describe("year over year", () => {
        it("lines up the two preceding years next to the selected one", () => {
            render(
                seed({
                    transactions: [
                        txn(1, { amount: -100_00, date: `${YEAR}-01-05` }),
                        txn(2, { amount: -200_00, date: `${PREV}-01-05` }),
                        txn(3, { amount: -300_00, date: `${YEAR - 2}-01-05` }),
                    ],
                }),
            );

            const jan = series("line-chart").find((r) => r.month === "Jan");
            expect(jan).toEqual({
                month: "Jan",
                [String(YEAR - 2)]: 300,
                [String(PREV)]: 200,
                [String(YEAR)]: 100,
            });
            // months with no data stay null so the line breaks instead of dipping to 0
            expect(series("line-chart").find((r) => r.month === "Feb")[String(YEAR)]).toBeNull();
        });
    });
});
