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
                    data-cols={JSON.stringify(series)}
                />
            );
        };
    return { BarChart: serialize("bar-chart"), LineChart: serialize("line-chart") };
});

import AnalyticsPage from "./AnalyticsPage.jsx";
import { renderUI, resetStore, screen, seed, within } from "../test/render.jsx";
import { computeRange } from "../engine/budget.js";
import { PALETTE, SERIES } from "./chartTheme.js";

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

/** Whichever chart (bar or line) a card holds, parsed back to its data rows. */
function cardChart(title) {
    const card = screen.getByText(new RegExp(title)).closest(".chart-card");
    const chart = card.querySelector("[data-testid]");
    return {
        data: JSON.parse(chart.dataset.series),
        cols: JSON.parse(chart.dataset.cols),
        testid: chart.dataset.testid,
    };
}

const kpiColor = (label) => kpi(label).querySelector(".kpi__value").style.color;
const kpiSub = (label) => kpi(label).querySelector(".kpi__sub").textContent;

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

        it("names each year series and dims older ones toward the accent", () => {
            render(
                seed({
                    transactions: [
                        txn(1, { amount: -100_00, date: `${YEAR}-01-05` }),
                        txn(2, { amount: -200_00, date: `${PREV}-01-05` }),
                        txn(3, { amount: -300_00, date: `${YEAR - 2}-01-05` }),
                    ],
                }),
            );

            const yoy = cardChart("Expenses year over year");
            expect(yoy.cols).toEqual([
                { name: String(YEAR - 2), color: SERIES.hint },
                { name: String(PREV), color: SERIES.secondary },
                { name: String(YEAR), color: SERIES.accent },
            ]);

            const incomeYoy = cardChart("Income year over year");
            expect(incomeYoy.cols[2]).toEqual({ name: String(YEAR), color: SERIES.income });
        });

        it("splits income and expense onto their own year-over-year charts", () => {
            render(
                seed({
                    transactions: [
                        txn(1, { categoryId: 1, amount: 500_00, date: `${YEAR}-01-05` }),
                        txn(2, { amount: -100_00, date: `${YEAR}-01-05` }),
                    ],
                }),
            );

            const expJan = cardChart("Expenses year over year").data.find((r) => r.month === "Jan");
            const incJan = cardChart("Income year over year").data.find((r) => r.month === "Jan");
            expect(expJan[String(YEAR)]).toBe(100);
            expect(incJan[String(YEAR)]).toBe(500);
        });

        it("always gives the selected year the accent line, however many precede it", () => {
            render(seed({ transactions: [txn(1, { amount: -100_00, date: `${YEAR}-01-05` })] }));

            const yoy = cardChart("Expenses year over year");
            const current = yoy.cols[yoy.cols.length - 1];
            expect(current.name).toBe(String(YEAR));
            expect(current.color).toBe(SERIES.accent);
        });
    });

    describe("average income per month", () => {
        it("averages a full past year over exactly twelve months", async () => {
            const { user } = render(
                seed({
                    transactions: [
                        txn(1, { categoryId: 1, amount: 120_000_00, date: `${PREV}-06-15` }),
                    ],
                }),
            );

            await user.click(screen.getByRole("button", { name: String(YEAR) }));
            await user.click(document.querySelector(`[role="option"][value="${PREV}"]`));

            // 120 000 / 12 = 10 000
            expect(kpiValue("Avg income / month")).toBe(n("10 000 ₽"));
            expect(kpiSub("Avg income / month")).toBe("12 months");
        });

        it("labels the elapsed-months count for the current year and pluralizes it", () => {
            render(seed({ transactions: [] }));

            const months = now.getMonth() + 1;
            expect(kpiSub("Avg income / month")).toBe(`${months} month${months === 1 ? "" : "s"}`);
        });
    });

    describe("kpi colors", () => {
        it("greens a positive net and savings rate, reds a negative net", async () => {
            const { user } = render(
                seed({
                    transactions: [
                        txn(1, { categoryId: 1, amount: 100_00, date: `${YEAR}-01-05` }),
                        txn(2, { amount: -300_00, date: `${YEAR}-01-06` }),
                        txn(3, { categoryId: 1, amount: 100_00, date: `${PREV}-01-05` }),
                        txn(4, { amount: -10_00, date: `${PREV}-01-06` }),
                    ],
                }),
            );

            // this year: net is negative (-200), so red
            expect(kpiColor("Net saved")).toBe("var(--m-expense)");
            expect(kpiColor("Savings rate")).toBe("var(--m-expense)");

            await user.click(screen.getByRole("button", { name: String(YEAR) }));
            await user.click(document.querySelector(`[role="option"][value="${PREV}"]`));

            // previous year: net positive, so green
            expect(kpiColor("Net saved")).toBe("var(--m-income)");
            expect(kpiColor("Savings rate")).toBe("var(--m-income)");
        });

        it("dashes savings rate when there was no income", () => {
            render(seed({ transactions: [txn(1, { amount: -300_00, date: `${YEAR}-01-06` })] }));
            expect(kpiValue("Savings rate")).toBe("—");
        });

        it("greens a high budget hit rate", () => {
            render(
                seed({
                    budgets: [{ categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 }],
                    transactions: [txn(1, { categoryId: 2, amount: -1_00, date: `${YEAR}-01-10` })],
                }),
            );
            // the only active envelope stayed within budget -> 100%
            expect(kpiValue("Budget hit rate")).toBe("100%");
            expect(kpiColor("Budget hit rate")).toBe("var(--m-income)");
        });

        it("ambers a hit rate between 60 and 80", () => {
            // Two categories, each budgeted 10 000 in Jan. Spending the envelope
            // exactly leaves no surplus to roll over, so each is one active month:
            // Groceries hits (spent == available), Rent overshoots -> 3 hits / 4 = 75%.
            render(
                seed({
                    budgets: [
                        { categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 },
                        { categoryId: 2, year: YEAR, month: 2, amount: 10_000_00 },
                        { categoryId: 3, year: YEAR, month: 1, amount: 10_000_00 },
                        { categoryId: 3, year: YEAR, month: 2, amount: 10_000_00 },
                    ],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -10_000_00, date: `${YEAR}-01-10` }),
                        txn(2, { categoryId: 2, amount: -10_000_00, date: `${YEAR}-02-10` }),
                        txn(3, { categoryId: 3, amount: -10_000_00, date: `${YEAR}-01-10` }),
                        txn(4, { categoryId: 3, amount: -30_000_00, date: `${YEAR}-02-10` }),
                    ],
                }),
            );
            expect(kpiValue("Budget hit rate")).toBe("75%");
            expect(kpiColor("Budget hit rate")).toBe("var(--m-warning)");
        });

        it("reds a hit rate below 60", () => {
            // both active envelopes blown -> 0% -> red
            render(
                seed({
                    budgets: [
                        { categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 },
                        { categoryId: 3, year: YEAR, month: 1, amount: 10_000_00 },
                    ],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -30_000_00, date: `${YEAR}-01-10` }),
                        txn(2, { categoryId: 3, amount: -30_000_00, date: `${YEAR}-01-10` }),
                    ],
                }),
            );
            expect(kpiValue("Budget hit rate")).toBe("0%");
            expect(kpiColor("Budget hit rate")).toBe("var(--m-expense)");
        });

        it("greys the over-budget figure when nothing overran", () => {
            render(
                seed({
                    budgets: [{ categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 }],
                    transactions: [txn(1, { categoryId: 2, amount: -1_00, date: `${YEAR}-01-10` })],
                }),
            );
            expect(kpiValue("Over budget")).toBe(n("0 ₽"));
            expect(kpiColor("Over budget")).toBe("var(--m-text-faint)");
            expect(kpiSub("Over budget")).toBe("no overruns");
        });

        it("reds the over-budget figure and names the worst category when something overran", () => {
            render(
                seed({
                    budgets: [{ categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 }],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -12_000_00, date: `${YEAR}-01-10` }),
                    ],
                }),
            );
            expect(kpiColor("Over budget")).toBe("var(--m-expense)");
            expect(kpiSub("Over budget")).toBe("worst: Groceries");
        });
    });

    describe("categories through the year", () => {
        const catSeed = () =>
            seed({
                transactions: [
                    txn(1, { categoryId: 2, amount: -300_00, date: `${YEAR}-01-10` }),
                    txn(2, { categoryId: 3, amount: -100_00, date: `${YEAR}-02-10` }),
                ],
            });

        it("stacks rounded ruble amounts per category and month", () => {
            render(catSeed());

            const chart = cardChart("Categories through the year");
            const jan = chart.data.find((r) => r.month === "Jan");
            const groceries = chart.cols.find((c) => c.label === "Groceries");
            const rent = chart.cols.find((c) => c.label === "Rent");
            expect(jan[groceries.name]).toBe(300);
            const feb = chart.data.find((r) => r.month === "Feb");
            expect(feb[rent.name]).toBe(100);
            expect(jan[rent.name]).toBe(0);
        });

        it("keys named categories as cat-<id> and colors them from the palette", () => {
            render(catSeed());

            const chart = cardChart("Categories through the year");
            const groceries = chart.cols.find((c) => c.label === "Groceries");
            expect(groceries.name).toBe("cat-2");
            expect(groceries.color).toBe(PALETTE[0]);
        });

        it("blanks future months of the current year to null, not zero", () => {
            render(catSeed());

            const chart = cardChart("Categories through the year");
            const nowMonth = now.getMonth();
            const dec = chart.data[11];
            const someKey = chart.cols[0].name;
            if (nowMonth < 11) {
                expect(dec[someKey]).toBeNull();
            }
            // the current month itself is still filled
            expect(chart.data[nowMonth][someKey]).not.toBeNull();
        });

        it("switches the categories chart from bars to lines", async () => {
            const { user } = render(catSeed());

            const card = screen.getByText(/Categories through the year/).closest(".chart-card");
            expect(card.querySelector('[data-testid="bar-chart"]')).toBeTruthy();

            await user.click(within(card).getByRole("button", { name: "Stacked" }));
            await user.click(document.querySelector('[role="option"][value="lines"]'));

            expect(card.querySelector('[data-testid="line-chart"]')).toBeTruthy();
            expect(card.querySelector('[data-testid="bar-chart"]')).toBeFalsy();
        });

        it("says so when a year has no categorized income", () => {
            render(seed({ transactions: [txn(1, { amount: -100_00, date: `${YEAR}-01-10` })] }));

            expect(screen.getByText(`No categorized income in ${YEAR}`)).toBeInTheDocument();
        });
    });

    describe("weekday and day-of-month coloring", () => {
        it("paints weekend bars with the accent and weekdays from the palette", () => {
            const firstSat = 1 + ((6 - new Date(YEAR, 0, 1).getDay() + 7) % 7);
            const day = (d) => String(d).padStart(2, "0");
            render(
                seed({
                    transactions: [
                        txn(1, { amount: -50_00, date: `${YEAR}-01-${day(firstSat)}` }),
                        txn(2, { amount: -50_00, date: `${YEAR}-01-${day(firstSat + 2)}` }),
                    ],
                }),
            );

            const weekday = chartSeries("Spending by weekday");
            const sat = weekday.find((r) => r.day === "Sat");
            const mon = weekday.find((r) => r.day === "Mon");
            expect(sat.color).toBe(SERIES.accent);
            expect(mon.color).toBe(PALETTE[0]);
        });
    });

    describe("income stats", () => {
        it("counts income rows, reports the median and the largest", () => {
            render(
                seed({
                    transactions: [
                        txn(1, { categoryId: 1, amount: 100_00, date: `${YEAR}-01-03` }),
                        txn(2, {
                            categoryId: 1,
                            amount: 900_00,
                            date: `${YEAR}-02-03`,
                            description: "Bonus",
                        }),
                        txn(3, { categoryId: 1, amount: 500_00, date: `${YEAR}-03-03` }),
                    ],
                }),
            );

            const card = screen.getByText(/Income stats/).closest(".chart-card");
            const rows = [...card.querySelectorAll(".stat-list__row")].map((r) => r.textContent);
            expect(rows[0]).toContain("Income transactions3");
            expect(rows[1]).toContain(n("Median income500 ₽"));
            expect(rows[2]).toContain("Per month0");
            expect(rows[3]).toContain(n("Largest income"));
            expect(rows[3]).toContain(`Bonus · 03.02.${YEAR}`);
            expect(rows[3]).toContain(n("900 ₽"));
        });
    });

    describe("budget discipline cell classes", () => {
        const cellFor = (categoryName, monthIndex) =>
            screen
                .getByText(categoryName)
                .closest("tr")
                .querySelectorAll("td")
                [monthIndex + 1].querySelector(".disc-cell");

        it("marks exactly-on-budget as ok, not amber", () => {
            render(
                seed({
                    budgets: [{ categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 }],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -10_000_00, date: `${YEAR}-01-10` }),
                    ],
                }),
            );
            expect(cellFor("Groceries", 0)).toHaveClass("disc-cell_ok");
        });

        it("marks spend with no budget at all as the unbudgeted class", () => {
            render(
                seed({
                    budgets: [],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -5_000_00, date: `${YEAR}-01-10` }),
                    ],
                }),
            );
            const cell = cellFor("Groceries", 0);
            expect(cell).toHaveClass("disc-cell_nobudget");
            expect(cell).toHaveAttribute("title", expect.stringContaining("no budget"));
        });

        it("marks 120% exactly as amber and just over as red", () => {
            render(
                seed({
                    budgets: [
                        { categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 },
                        { categoryId: 3, year: YEAR, month: 1, amount: 10_000_00 },
                    ],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -12_000_00, date: `${YEAR}-01-10` }),
                        txn(2, { categoryId: 3, amount: -12_001_00, date: `${YEAR}-01-10` }),
                    ],
                }),
            );
            expect(cellFor("Groceries", 0)).toHaveClass("disc-cell_warn");
            expect(cellFor("Rent", 0)).toHaveClass("disc-cell_over");
        });
    });
});
