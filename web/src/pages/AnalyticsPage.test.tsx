import { beforeEach, describe, expect, it, vi } from "vitest";

// Real charts render an SVG whose numbers are unreadable from a test; each one
// is swapped for a node carrying the exact rows the page computed, so the
// plan-vs-fact colors and the yearly series are assertable.
vi.mock("@mantine/charts", () => {
    const serialize = (testid: string) =>
        function Chart({
            data,
            series,
            withLegend,
        }: {
            data: unknown;
            series: Array<{ name: string; label?: string }>;
            withLegend?: boolean;
        }) {
            return (
                <div
                    data-testid={testid}
                    data-series={JSON.stringify(data)}
                    data-cols={JSON.stringify(series)}
                >
                    {withLegend === true && (
                        <div data-testid={`${testid}-legend`}>
                            {series.map((item) => (
                                <span key={item.name}>{item.label ?? item.name}</span>
                            ))}
                        </div>
                    )}
                </div>
            );
        };
    return { BarChart: serialize("bar-chart"), LineChart: serialize("line-chart") };
});

import AnalyticsPage from "./AnalyticsPage.jsx";
import { renderUI, resetStore, screen, seed, within } from "../test/render.jsx";
import { computeRange } from "../engine/budget.js";
import { PALETTE, SERIES } from "./chartTheme.js";
import type { Snapshot, Transaction } from "../types.js";
import type { SnapshotPatch } from "../test/render.js";

interface ChartRow {
    [key: string]: string | number | null | undefined;
    month?: string;
    day?: string;
    Share?: number;
    Spent?: number;
    color?: string;
}
interface ChartColumn {
    name: string;
    label?: string;
    color?: string;
}

const FIRST_YEAR = 2020;
const now = new Date();
const YEAR = now.getFullYear();
const PREV = YEAR - 1;

/** Rows a mocked chart was handed, parsed back out of its `data-series`. */
function series(testid: string, index = 0): ChartRow[] {
    return JSON.parse(
        screen.getAllByTestId(testid)[index]!.dataset["series"] ?? "[]",
    ) as ChartRow[];
}

function chartSeries(title: string): ChartRow[] {
    const card = screen.getByText(new RegExp(title)).closest<HTMLElement>(".chart-card")!;
    return JSON.parse(
        card.querySelector<HTMLElement>('[data-testid="bar-chart"]')!.dataset["series"] ?? "[]",
    ) as ChartRow[];
}

/** Whichever chart (bar or line) a card holds, parsed back to its data rows. */
function cardChart(title: string): { data: ChartRow[]; cols: ChartColumn[]; testid: string } {
    const card = screen.getByText(new RegExp(title)).closest<HTMLElement>(".chart-card")!;
    const chart = card.querySelector<HTMLElement>("[data-testid]")!;
    return {
        data: JSON.parse(chart.dataset["series"] ?? "[]") as ChartRow[],
        cols: JSON.parse(chart.dataset["cols"] ?? "[]") as ChartColumn[],
        testid: chart.dataset["testid"] ?? "",
    };
}

const kpiColor = (label: string) =>
    kpi(label)!.querySelector<HTMLElement>(".kpi__value")!.style.color;
const kpiSub = (label: string) => kpi(label)!.querySelector<HTMLElement>(".kpi__sub")!.textContent;

// ru-RU groups thousands with a non-breaking space. Expected strings below are
// written with plain spaces throughout and only the digit groups swapped, so
// they stay readable while matching the rendered text exactly.
const n = (s: string) => s.replace(/(\d) (?=\d)/g, "$1\u00a0");

const kpi = (label: string) =>
    screen
        .getAllByText(label)
        .map((el) => el.closest<HTMLElement>(".kpi")!)
        .find(Boolean);
const kpiValue = (label: string) =>
    kpi(label)!.querySelector<HTMLElement>(".kpi__value")!.textContent;

const txn = (id: number, patch: Partial<Transaction> = {}): Partial<Transaction> => ({
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
function seedKnownYear(patch: SnapshotPatch = {}) {
    return seed({
        transactions: [
            txn(1, { categoryId: 1, amount: 300_000_00, date: `${YEAR}-01-15` }),
            txn(2, { categoryId: 2, amount: -60_000_00, date: `${YEAR}-01-20` }),
            txn(3, { categoryId: 3, amount: -40_000_00, date: `${YEAR}-01-25` }),
        ],
        ...patch,
    });
}

function render(snapshot: Snapshot, { lastYear = YEAR }: { lastYear?: number } = {}) {
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

            const cells = (year: string) =>
                [
                    ...[...document.querySelectorAll<HTMLElement>(".report-table tbody tr")]
                        .find((tr) => tr.firstChild!.textContent === year)!
                        .querySelectorAll<HTMLElement>("td"),
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

            const current = container.querySelectorAll<HTMLElement>(".report-table__row_current");
            expect(current).toHaveLength(1);
            expect(current[0]).toHaveTextContent(String(YEAR));
        });
    });

    describe("year selector", () => {
        it("offers every year up to today and never a future one", async () => {
            const { user } = render(seedKnownYear(), { lastYear: YEAR + 4 });

            await user.click(screen.getByRole("button", { name: String(YEAR) }));

            const offered = [...document.querySelectorAll<HTMLElement>('[role="option"]')].map(
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
            await user.click(
                document.querySelector<HTMLElement>(`[role="option"][value="${PREV}"]`)!,
            );

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

        const januaryCell = (categoryName: string) =>
            screen
                .getByText(categoryName, { selector: ".disc-grid__name" })
                .closest<HTMLElement>("tr")!
                .querySelectorAll<HTMLElement>("td")[1]!
                .querySelector<HTMLElement>(".disc-cell")!;

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
            const day = (value: number) => String(value).padStart(2, "0");
            render(
                seed({
                    transactions: [
                        txn(1, { amount: -75_00, date: `${YEAR}-01-${day(firstMonday)}` }),
                        txn(2, { amount: -25_00, date: `${YEAR}-01-${day(firstMonday + 5)}` }),
                    ],
                }),
            );

            const weekday = chartSeries("Spending by weekday");
            expect(weekday.find((r) => r.day === "Mon")!.Share).toBe(75);
            expect(weekday.find((r) => r.day === "Sat")!.Share).toBe(25);
            expect(weekday.filter((r) => r.Share! > 0)).toHaveLength(2);
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
            expect(dom.find((r) => r.day === "3")!.Spent).toBe(500);
            expect(dom.find((r) => r.day === "17")!.Spent).toBe(50);
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

            const stats = screen
                .getByText(/Transaction stats/)
                .closest<HTMLElement>(".chart-card")!;
            const rows = [...stats.querySelectorAll<HTMLElement>(".stat-list__row")].map(
                (r) => r.textContent,
            );
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
            expect(series("line-chart").find((r) => r.month === "Feb")![String(YEAR)]).toBeNull();
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
            expect(expJan![String(YEAR)]).toBe(100);
            expect(incJan![String(YEAR)]).toBe(500);
        });

        it("always gives the selected year the accent line, however many precede it", () => {
            render(seed({ transactions: [txn(1, { amount: -100_00, date: `${YEAR}-01-05` })] }));

            const yoy = cardChart("Expenses year over year");
            const current = yoy.cols[yoy.cols.length - 1];
            expect(current!.name).toBe(String(YEAR));
            expect(current!.color).toBe(SERIES.accent);
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
            await user.click(
                document.querySelector<HTMLElement>(`[role="option"][value="${PREV}"]`)!,
            );

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
            await user.click(
                document.querySelector<HTMLElement>(`[role="option"][value="${PREV}"]`)!,
            );

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
            expect(jan![groceries!.name]).toBe(300);
            const feb = chart.data.find((r) => r.month === "Feb");
            expect(feb![rent!.name]).toBe(100);
            expect(jan![rent!.name]).toBe(0);
        });

        it("keys named categories as cat-<id> and colors them from the palette", () => {
            render(catSeed());

            const chart = cardChart("Categories through the year");
            const groceries = chart.cols.find((c) => c.label === "Groceries");
            expect(groceries!.name).toBe("cat-2");
            expect(groceries!.color).toBe(PALETTE[0]);
        });

        it("blanks future months of the current year to null, not zero", () => {
            render(catSeed());

            const chart = cardChart("Categories through the year");
            const nowMonth = now.getMonth();
            const dec = chart.data[11];
            const someKey = chart.cols[0]!.name;
            if (nowMonth < 11) {
                expect(dec![someKey]).toBeNull();
            }
            // the current month itself is still filled
            expect(chart.data[nowMonth]![someKey]).not.toBeNull();
        });

        it("switches the categories chart from bars to lines", async () => {
            const { user } = render(catSeed());

            const card = screen
                .getByText(/Categories through the year/)
                .closest<HTMLElement>(".chart-card")!;
            expect(card.querySelector<HTMLElement>('[data-testid="bar-chart"]')!).toBeTruthy();

            await user.click(within(card).getByRole("button", { name: "Stacked" }));
            await user.click(
                document.querySelector<HTMLElement>('[role="option"][value="lines"]')!,
            );

            expect(card.querySelector<HTMLElement>('[data-testid="line-chart"]')!).toBeTruthy();
            expect(card.querySelector<HTMLElement>('[data-testid="bar-chart"]')!).toBeFalsy();
        });

        it("says so when a year has no categorized income", () => {
            render(seed({ transactions: [txn(1, { amount: -100_00, date: `${YEAR}-01-10` })] }));

            expect(screen.getByText(`No categorized income in ${YEAR}`)).toBeInTheDocument();
        });
    });

    describe("weekday and day-of-month coloring", () => {
        it("paints weekend bars with the accent and weekdays from the palette", () => {
            const firstSat = 1 + ((6 - new Date(YEAR, 0, 1).getDay() + 7) % 7);
            const day = (value: number) => String(value).padStart(2, "0");
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
            expect(sat!.color).toBe(SERIES.accent);
            expect(mon!.color).toBe(PALETTE[0]);
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

            const card = screen.getByText(/Income stats/).closest<HTMLElement>(".chart-card")!;
            const rows = [...card.querySelectorAll<HTMLElement>(".stat-list__row")].map(
                (r) => r.textContent,
            );
            expect(rows[0]).toContain("Income transactions3");
            expect(rows[1]).toContain(n("Median income500 ₽"));
            expect(rows[2]).toContain("Per month0");
            expect(rows[3]).toContain(n("Largest income"));
            expect(rows[3]).toContain(`Bonus · 03.02.${YEAR}`);
            expect(rows[3]).toContain(n("900 ₽"));
        });
    });

    describe("budget discipline cell classes", () => {
        const cellFor = (categoryName: string, monthIndex: number) =>
            screen
                .getByText(categoryName, { selector: ".disc-grid__name" })
                .closest<HTMLElement>("tr")!
                .querySelectorAll<HTMLElement>("td")
                [monthIndex + 1]!.querySelector<HTMLElement>(".disc-cell")!;

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

        it("leaves a month with no available budget and no spend classless", () => {
            // Jan budget 10 000 fully spent leaves zero surplus to roll into Feb,
            // which has no budget of its own and no spend — available 0, spent 0,
            // ratio null → no class. Pins discClass's `cell.ratio == null` guard
            // (mutating to `!= null` would tag the empty cell) and its `return ""`.
            render(
                seed({
                    budgets: [{ categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 }],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -10_000_00, date: `${YEAR}-01-10` }),
                    ],
                }),
            );
            const feb = cellFor("Groceries", 1);
            expect(feb.classList).toHaveLength(1);
            expect(feb).toHaveClass("disc-cell");
            expect(feb).not.toHaveClass("disc-cell_ok");
            expect(feb).not.toHaveClass("disc-cell_nobudget");
            expect(feb).toHaveAttribute("title", n("Groceries · Feb: —"));
        });

        it("prints the ratio percentage and only spells carry-over when it differs", () => {
            // January: 5 000 of a 10 000 budget = 50%; nothing rolled in, so
            // available == budgeted and no carry-over clause. February inherits the
            // 5 000 surplus on top of its own 10 000, so available (15 000) differs
            // from budgeted (10 000) and the carry-over clause appears. Pins
            // `Math.round(cell.ratio * 100)` and the `available !== budgeted` gate.
            render(
                seed({
                    budgets: [
                        { categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 },
                        { categoryId: 2, year: YEAR, month: 2, amount: 10_000_00 },
                    ],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -5_000_00, date: `${YEAR}-01-10` }),
                    ],
                }),
            );
            expect(cellFor("Groceries", 0)).toHaveAttribute(
                "title",
                n("Groceries · Jan: 5 000 / 10 000 ₽ (50%)"),
            );
            expect(cellFor("Groceries", 1)).toHaveAttribute(
                "title",
                n("Groceries · Feb: 0 / 15 000 ₽ (0%) · budgeted 10 000 + carry-over"),
            );
        });
    });

    describe("mutation-hardening", () => {
        it("renders category names instead of internal keys in the chart legend", () => {
            render(seedKnownYear());

            const card = screen
                .getByText(/Categories through the year/)
                .closest<HTMLElement>(".chart-card")!;
            const legend = within(card).getByTestId("bar-chart-legend");

            expect(within(legend).getByText("Groceries")).toBeInTheDocument();
            expect(within(legend).getByText("Rent")).toBeInTheDocument();
            expect(within(legend).queryByText("cat-2")).not.toBeInTheDocument();
            expect(within(legend).queryByText("cat-3")).not.toBeInTheDocument();
        });

        it("suffixes the group name only when two categories share a name", () => {
            // Two distinct "Fuel" categories in different groups collide on name,
            // so both series labels carry the group name; the unique "Groceries"
            // label stays bare. Pins the seen-counter (`> 1`) and its arithmetic.
            render(
                seed({
                    groups: [
                        { id: 1, name: "Income", kind: "income", sort: 1 },
                        { id: 2, name: "Car", kind: "expense", sort: 2 },
                        { id: 3, name: "Home", kind: "expense", sort: 3 },
                    ],
                    categories: [
                        { id: 1, groupId: 1, name: "Salary", sort: 1, archived: false },
                        { id: 2, groupId: 2, name: "Fuel", sort: 1, archived: false },
                        { id: 3, groupId: 3, name: "Fuel", sort: 2, archived: false },
                        { id: 4, groupId: 2, name: "Groceries", sort: 3, archived: false },
                    ],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -100_00, date: `${YEAR}-01-10` }),
                        txn(2, { categoryId: 3, amount: -200_00, date: `${YEAR}-01-10` }),
                        txn(3, { categoryId: 4, amount: -300_00, date: `${YEAR}-01-10` }),
                    ],
                }),
            );
            const labels = cardChart("Categories through the year").cols.map((c) => c.label);
            expect(labels).toContain("Fuel · Car");
            expect(labels).toContain("Fuel · Home");
            expect(labels).toContain("Groceries");
            expect(labels).not.toContain("Fuel");
        });

        it("fills the current month but blanks strictly-later ones", () => {
            // Spend in every month; the current-year chart keeps months up to and
            // including now, and nulls only months strictly after. Pins
            // `m > blankAfter` against `>=` (would null the current month) and
            // `<=` (would null every earlier month).
            const nowMonth = now.getMonth();
            const txs = [];
            for (let m = 0; m <= nowMonth; m++) {
                txs.push(
                    txn(m + 1, {
                        categoryId: 2,
                        amount: -100_00,
                        date: `${YEAR}-${String(m + 1).padStart(2, "0")}-10`,
                    }),
                );
            }
            render(seed({ transactions: txs }));
            const chart = cardChart("Categories through the year");
            const key = chart.cols[0]!.name;
            expect(chart.data[0]![key]).toBe(100);
            expect(chart.data[nowMonth]![key]).toBe(100);
            if (nowMonth < 11) {
                expect(chart.data[nowMonth + 1]![key]).toBeNull();
                expect(chart.data[11]![key]).toBeNull();
            }
        });

        it("assigns the neutral hint color to the folded Other band", () => {
            // More categories than the palette holds forces an "other" fold; its
            // series uses SERIES.hint, not a palette hue. Pins the
            // `r.id == null ? SERIES.hint : PALETTE[...]` branch.
            const cats = [{ id: 1, groupId: 1, name: "Salary", sort: 1, archived: false }];
            const txs = [];
            const limit = PALETTE.length;
            for (let i = 0; i < limit + 3; i++) {
                const id = 100 + i;
                cats.push({ id, groupId: 2, name: `Cat${i}`, sort: i + 1, archived: false });
                txs.push(
                    txn(id, {
                        categoryId: id,
                        amount: -(limit + 3 - i) * 100_00,
                        date: `${YEAR}-01-10`,
                    }),
                );
            }
            render(
                seed({
                    groups: [
                        { id: 1, name: "Income", kind: "income", sort: 1 },
                        { id: 2, name: "Living", kind: "expense", sort: 2 },
                    ],
                    categories: cats,
                    transactions: txs,
                }),
            );
            const cols = cardChart("Categories through the year").cols;
            const other = cols.find((c) => c.name === "other");
            expect(other).toBeTruthy();
            expect(other!.color).toBe(SERIES.hint);
            expect(cols.filter((c) => c.color === SERIES.hint)).toHaveLength(1);
        });

        it("dims the years right-aligned when fewer than three precede the selection", () => {
            // firstYear = PREV, so only two years qualify: yrs.length is 2 and the
            // offset 3-2=1 pushes the colors into secondary+accent (skipping hint).
            // Pins `dims[i + (3 - yrs.length)]` for the offset.
            const snap = seed({
                transactions: [
                    txn(1, { amount: -100_00, date: `${YEAR}-01-05` }),
                    txn(2, { amount: -200_00, date: `${PREV}-01-05` }),
                ],
            });
            const results = computeRange(snap, PREV, YEAR);
            renderUI(<AnalyticsPage results={results} firstYear={PREV} lastYear={YEAR} />);

            const yoy = cardChart("Expenses year over year");
            expect(yoy.cols).toEqual([
                { name: String(PREV), color: SERIES.secondary },
                { name: String(YEAR), color: SERIES.accent },
            ]);
        });

        it("weights the weekday shares as a percentage of the year total", () => {
            // Mon 75, Sat 25 out of 100 → 75% and 25%. Pins `(v / total) * 100`
            // against `v / total / 100` (would floor to 0) and the round.
            const firstMonday = 1 + ((8 - new Date(YEAR, 0, 1).getDay()) % 7);
            const day = (value: number) => String(value).padStart(2, "0");
            render(
                seed({
                    transactions: [
                        txn(1, { amount: -75_00, date: `${YEAR}-01-${day(firstMonday)}` }),
                        txn(2, { amount: -25_00, date: `${YEAR}-01-${day(firstMonday + 5)}` }),
                    ],
                }),
            );
            const weekday = chartSeries("Spending by weekday");
            expect(weekday.find((r) => r.day === "Mon")!.Share).toBe(75);
            expect(weekday.find((r) => r.day === "Sat")!.Share).toBe(25);
        });

        it("labels day-of-month bars 1..31 and rounds their rubles", () => {
            // 350 kopeck-rounded spends land on the 1st; the axis label is the
            // 1-based day. Pins `String(i + 1)` and `Math.round(v / 100)`.
            render(
                seed({
                    transactions: [txn(1, { amount: -350_00, date: `${YEAR}-01-01` })],
                }),
            );
            const dom = chartSeries("Spending by day of month");
            expect(dom[0]).toEqual({ day: "1", Spent: 350 });
            expect(dom[30]!.day).toBe("31");
        });

        it("greys the over-budget KPI at exactly zero overrun", () => {
            // A perfectly-on-budget envelope leaves totalOverrun at 0, which must
            // read as the faint color, not red. Pins `totalOverrun > 0` against
            // `>= 0`.
            render(
                seed({
                    budgets: [{ categoryId: 2, year: YEAR, month: 1, amount: 10_000_00 }],
                    transactions: [
                        txn(1, { categoryId: 2, amount: -10_000_00, date: `${YEAR}-01-10` }),
                    ],
                }),
            );
            expect(kpiValue("Over budget")).toBe(n("0 ₽"));
            expect(kpiColor("Over budget")).toBe("var(--m-text-faint)");
        });

        it("pluralizes the elapsed-month label everywhere but January", () => {
            render(seed({ transactions: [] }));
            const months = now.getMonth() + 1;
            const sub = kpiSub("Avg income / month");
            if (months === 1) {
                expect(sub).toBe("1 month");
            } else {
                expect(sub).toBe(`${months} months`);
                expect(sub).not.toBe(`${months} month`);
            }
        });

        it("colors the report table's net column by its sign", () => {
            // PREV net is negative (spent more than earned), YEAR net positive.
            // Pins `r.net >= 0` per row and the current-row class on the selected
            // year only.
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
            const rowFor = (year: string) =>
                [...document.querySelectorAll<HTMLElement>(".report-table tbody tr")].find(
                    (tr) => tr.firstChild!.textContent === year,
                );
            const netCell = (year: string) => rowFor(year)!.querySelectorAll<HTMLElement>("td")[3];
            expect(netCell(String(PREV))!.style.color).toBe("var(--m-expense)");
            expect(netCell(String(YEAR))!.style.color).toBe("var(--m-income)");
            expect(rowFor(String(YEAR))).toHaveClass("report-table__row_current");
            expect(rowFor(String(PREV))).not.toHaveClass("report-table__row_current");
        });

        it("dashes the report table's rate when a year had no income", () => {
            // PREV had only spending, so its savingsRate is null → "—"; YEAR earned
            // and shows a percentage. Pins `r.savingsRate != null`.
            render(
                seed({
                    transactions: [
                        txn(1, { categoryId: 1, amount: 300_000_00, date: `${YEAR}-01-15` }),
                        txn(2, { categoryId: 2, amount: -100_000_00, date: `${YEAR}-01-20` }),
                        txn(3, { categoryId: 2, amount: -50_000_00, date: `${PREV}-04-20` }),
                    ],
                }),
            );
            const rateCell = (year: string) =>
                [...document.querySelectorAll<HTMLElement>(".report-table tbody tr")]
                    .find((tr) => tr.firstChild!.textContent === year)!
                    .querySelectorAll<HTMLElement>("td")[4]!.textContent;
            expect(rateCell(String(PREV))).toBe("—");
            expect(rateCell(String(YEAR))).toBe("67%");
        });
    });
});
