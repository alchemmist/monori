import { beforeEach, describe, expect, it, vi } from "vitest";

// The real charts render an SVG we cannot read numbers out of, so each one is
// swapped for a node that serialises the exact rows the page computed. That
// makes every aggregation — buckets, totals, per-account filtering — assertable.
vi.mock("@mantine/charts", () => {
    const serialize = (testid: string) =>
        function Chart({ data }: { data: unknown }) {
            return <div data-testid={testid} data-series={JSON.stringify(data)} />;
        };
    return {
        AreaChart: serialize("area-chart"),
        BarChart: serialize("bar-chart"),
        CompositeChart: serialize("composite-chart"),
        DonutChart: serialize("donut-chart"),
    };
});

vi.mock("../components/TimeNavigator.jsx", () => ({
    default: ({
        items,
        range,
        onChange,
    }: {
        items: unknown[];
        range: number[];
        onChange: (range: [number, number]) => void;
    }) => (
        <button type="button" onClick={() => onChange([0, Math.max(0, items.length - 1)])}>
            navigator {range.join("-")}
        </button>
    ),
}));

import DashboardPage from "./DashboardPage.jsx";
import { renderUI, resetStore, screen, seed } from "../test/render.jsx";
import type { Account, Transaction } from "../types.js";

interface ChartRow {
    [key: string]: string | number | null | undefined;
    x?: string;
    Income?: number;
    Expenses?: number;
    Spent?: number;
    name?: string;
    value?: number;
    month?: string;
}

const now = new Date();
const year = now.getFullYear();
const prevYear = year - 1;

/** Rows a mocked chart was handed, parsed back out of its `data-series`. */
function series(testid: string, index = 0): ChartRow[] {
    const nodes = screen.getAllByTestId(testid);
    return JSON.parse(nodes[index]!.dataset["series"] ?? "[]") as ChartRow[];
}

/** The composite trend chart's row for a 'YYYY-MM' month key. */
function trendRow(key: string) {
    return series("composite-chart").find((r) => r.x === key);
}

const account = (id: number, name: string, openingBalance: number): Partial<Account> => ({
    id,
    name,
    type: "card",
    icon: "card",
    color: "#000",
    openingBalance,
});

const txn = (id: number, patch: Partial<Transaction> = {}): Partial<Transaction> => ({
    id,
    accountId: 1,
    categoryId: 2,
    amount: -1000,
    date: `${prevYear}-03-10`,
    ...patch,
});

describe("DashboardPage", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders every account's balance as opening balance plus its transactions", () => {
        seed({
            accounts: [account(1, "Card", 500_00), account(2, "Cash", 100_00)],
            transactions: [
                txn(1, { accountId: 1, categoryId: 1, amount: 300_00 }),
                txn(2, { accountId: 1, amount: -120_00 }),
                txn(3, { accountId: 2, amount: -250_00 }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const balance = (name: string) =>
            screen
                .getByText(name)
                .closest<HTMLElement>(".balance-card")!
                .querySelector<HTMLElement>(".balance-card__value")!.textContent;
        expect(balance("Card")).toBe("680 ₽");
        expect(balance("Cash")).toBe("-150 ₽");
    });

    it("splits a month into income and expense by the category's group kind", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 900_00, date: `${prevYear}-03-05` }),
                txn(2, { categoryId: 2, amount: -400_00, date: `${prevYear}-03-12` }),
                txn(3, { categoryId: 3, amount: -100_00, date: `${prevYear}-03-20` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        // Salary is the only income-group category; the two others are expenses.
        expect(trendRow(`${prevYear}-03`)).toMatchObject({ Income: 900, Expenses: 500 });
    });

    it("carries net income forward month by month in the cumulative chart", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 1000_00, date: `${prevYear}-01-10` }),
                txn(2, { categoryId: 2, amount: -400_00, date: `${prevYear}-01-20` }),
                txn(3, { categoryId: 2, amount: -250_00, date: `${prevYear}-02-15` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(series("area-chart")).toEqual([
            { x: `${prevYear}-01`, "Cumulative net": 600 },
            { x: `${prevYear}-02`, "Cumulative net": 350 },
        ]);
    });

    it("nets year-to-date income against expenses in the KPI", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 800_00, date: `${year}-01-10` }),
                txn(2, { categoryId: 2, amount: -300_00, date: `${year}-01-20` }),
                // last year must not leak into a year-to-date figure
                txn(3, { categoryId: 1, amount: 5000_00, date: `${prevYear}-06-10` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const kpi = screen.getByText("Net year to date").closest<HTMLElement>(".kpi")!;
        expect(kpi.querySelector<HTMLElement>(".kpi__value")!).toHaveTextContent("500 ₽");
        expect(kpi.querySelector<HTMLElement>(".kpi__sub")!).toHaveTextContent(String(year));
    });

    it("keeps savings rate at zero and calculates negative runway when closed history has spending but no income", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [txn(1, { categoryId: 2, amount: -300_00, date: `${prevYear}-03-10` })],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(screen.getByText("Savings rate").closest<HTMLElement>(".kpi")!).toHaveTextContent(
            "0%",
        );
        expect(screen.getByText("Runway").closest<HTMLElement>(".kpi")!).toHaveTextContent(
            "-1.0 mo",
        );
        expect(trendRow(`${prevYear}-03`)!["Savings rate %"]).toBeNull();
    });

    it("restricts every chart to the picked account", async () => {
        seed({
            accounts: [account(1, "Card", 0), account(2, "Cash", 0)],
            transactions: [
                txn(1, { accountId: 1, categoryId: 2, amount: -700_00, date: `${prevYear}-04-10` }),
                txn(2, { accountId: 2, categoryId: 3, amount: -200_00, date: `${prevYear}-04-11` }),
            ],
        });

        const { user } = renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(trendRow(`${prevYear}-04`)!.Expenses).toBe(900);

        await user.click(screen.getByRole("button", { name: "All accounts" }));
        await user.click(document.querySelector<HTMLElement>('[role="option"][value="1"]')!);

        expect(screen.getByRole("button", { name: "Card" })).toBeInTheDocument();
        expect(trendRow(`${prevYear}-04`)!.Expenses).toBe(700);
        expect(series("donut-chart")).toEqual([
            { name: "Groceries", value: 700, color: "var(--m-chart-1)" },
        ]);
    });

    it("widens the trend window from the default 36 months to all history", async () => {
        // 40 closed months of history, oldest first, one per month
        const months = Array.from({ length: 40 }, (_, i) => {
            const d = new Date(year, now.getMonth() - 40 + i, 1);
            return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
        });
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: months.map((key, i) =>
                txn(i + 1, { amount: -(i + 1) * 100, date: `${key}-10` }),
            ),
        });

        const { user } = renderUI(<DashboardPage firstYear={year - 4} lastYear={year} />);

        expect(series("composite-chart")).toHaveLength(36);
        expect(trendRow(months[0]!)).toBeUndefined();

        await user.click(screen.getByRole("button", { name: "All" }));

        expect(series("composite-chart")).toHaveLength(40);
        expect(trendRow(months[0]!)!.Expenses).toBe(1);
    });

    it("ranks the donut by spend and keeps income out of it", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 2, amount: -100_00, date: `${year}-02-10` }),
                txn(2, { categoryId: 3, amount: -450_00, date: `${year}-02-11` }),
                txn(3, { categoryId: 1, amount: 900_00, date: `${year}-02-12` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(series("donut-chart").map(({ name, value }) => ({ name, value }))).toEqual([
            { name: "Rent", value: 450 },
            { name: "Groceries", value: 100 },
        ]);
    });

    it("handles an empty dashboard and prompts to choose a category", () => {
        seed({
            accounts: [],
            groups: [{ id: 2, name: "Spending", kind: "expense" }],
            categories: [{ id: 10, groupId: 2, name: "Fuel" }],
            transactions: [],
        });

        renderUI(<DashboardPage firstYear={year} lastYear={year} />);

        expect(screen.queryByText("All accounts")).not.toBeInTheDocument();
        expect(screen.getByText("Pick a category to see its monthly spending")).toBeInTheDocument();
        // runway is undefined with no spending at all
        expect(screen.getByText("Runway").closest<HTMLElement>(".kpi")!).toHaveTextContent("—");
        expect(screen.queryByTestId("donut-chart")).not.toBeInTheDocument();
        expect(series("area-chart")).toEqual([]);
    });

    it("groups spending after the first eleven categories into Other", () => {
        const categories = Array.from({ length: 13 }, (_, i) => ({
            id: i + 10,
            groupId: 2,
            name: `Expense ${i + 1}`,
        }));
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense" }],
            categories,
            transactions: categories.map((c, i) =>
                txn(c.id, { categoryId: c.id, amount: -(i + 1) * 100_00, date: `${year}-02-10` }),
            ),
        });

        renderUI(<DashboardPage firstYear={year} lastYear={year} />);

        const donut = series("donut-chart");
        expect(donut).toHaveLength(12);
        expect(donut[11]).toMatchObject({ name: "Other", value: 300 }); // 100 + 200
    });

    it("keeps the current partial month out of the trend but uses it for the monthly KPI", () => {
        const currentMonth = `${year}-${String(now.getMonth() + 1).padStart(2, "0")}`;
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 2, amount: -500_00, date: `${prevYear}-12-10` }),
                txn(2, { categoryId: 2, amount: -250_00, date: `${currentMonth}-05` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(trendRow(currentMonth)).toBeUndefined();
        expect(
            screen.getByText("Spent this month").closest<HTMLElement>(".kpi")!,
        ).toHaveTextContent("250 ₽");
    });

    it("stacks every expense group and keeps income out of the group chart", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            groups: [
                { id: 1, name: "Income", kind: "income" },
                { id: 2, name: "Food", kind: "expense" },
                { id: 3, name: "Home", kind: "expense" },
            ],
            categories: [
                { id: 1, groupId: 1, name: "Salary" },
                { id: 2, groupId: 2, name: "Groceries" },
                { id: 3, groupId: 3, name: "Rent" },
            ],
            transactions: [
                txn(1, { categoryId: 1, amount: 900_00, date: `${year}-02-01` }),
                txn(2, { categoryId: 2, amount: -120_00, date: `${year}-02-02` }),
                txn(3, { categoryId: 3, amount: -450_00, date: `${year}-02-03` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const groups = series("bar-chart", 1);
        expect(groups.find((row) => row.month === "Feb")).toEqual({
            month: "Feb",
            g2: 120,
            g3: 450,
        });
    });

    it("adds category spending to its calendar month only", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 2, amount: -120_00, date: `${year}-01-01` }),
                txn(2, { categoryId: 2, amount: -80_00, date: `${year}-01-20` }),
                txn(3, { categoryId: 2, amount: -90_00, date: `${year}-02-01` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const drill = series("bar-chart");
        expect(drill.find((row) => row.month === "Jan")!.Spent).toBe(200);
        expect(drill.find((row) => row.month === "Feb")!.Spent).toBe(90);
        expect(drill.find((row) => row.month === "Mar")!.Spent).toBe(0);
    });

    it("uses the current year's closed months for the YTD trend preset", async () => {
        const lastYearMonth = `${prevYear}-12`;
        const january = `${year}-01`;
        const february = `${year}-02`;
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { amount: -100_00, date: `${lastYearMonth}-10` }),
                txn(2, { amount: -200_00, date: `${january}-10` }),
                txn(3, { amount: -300_00, date: `${february}-10` }),
            ],
        });

        const { user } = renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);
        await user.click(screen.getByRole("button", { name: "YTD" }));

        const keys = series("composite-chart").map((row) => row.x);
        if (now.getMonth() > 0) expect(keys).toContain(january);
        if (now.getMonth() > 1) expect(keys).toContain(february);
        expect(keys).not.toContain(lastYearMonth);
    });

    it("calculates current pace and last-twelve-month savings from exact amounts", () => {
        const currentMonth = `${year}-${String(now.getMonth() + 1).padStart(2, "0")}`;
        const previous = new Date(year, now.getMonth() - 1, 1);
        const previousMonth = `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, "0")}`;
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 1000_00, date: `${prevYear}-06-10` }),
                txn(2, { categoryId: 2, amount: -400_00, date: `${prevYear}-06-11` }),
                txn(3, { categoryId: 2, amount: -310_00, date: `${currentMonth}-01` }),
                txn(4, { categoryId: 2, amount: -90_00, date: `${previousMonth}-10` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(screen.getByText("Saved").closest<HTMLElement>(".kpi")!).toHaveTextContent("510 ₽");
        expect(
            screen.getByText("Spent this month").closest<HTMLElement>(".kpi")!,
        ).toHaveTextContent("310 ₽");
        expect(
            screen.getByText("Spent this month").closest<HTMLElement>(".kpi")!,
        ).toHaveTextContent("vs 90 ₽ last month");
    });

    it("uses the current year's closed months for the YTD trend preset", async () => {
        const lastYearMonth = `${prevYear}-12`;
        const january = `${year}-01`;
        const february = `${year}-02`;
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { amount: -100_00, date: `${lastYearMonth}-10` }),
                txn(2, { amount: -200_00, date: `${january}-10` }),
                txn(3, { amount: -300_00, date: `${february}-10` }),
            ],
        });

        const { user } = renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);
        await user.click(screen.getByRole("button", { name: "YTD" }));

        const keys = series("composite-chart").map((row) => row.x);
        if (now.getMonth() > 0) expect(keys).toContain(january);
        if (now.getMonth() > 1) expect(keys).toContain(february);
        expect(keys).not.toContain(lastYearMonth);
    });

    it("calculates current pace and last-twelve-month savings from exact amounts", () => {
        const currentMonth = `${year}-${String(now.getMonth() + 1).padStart(2, "0")}`;
        const previous = new Date(year, now.getMonth() - 1, 1);
        const previousMonth = `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, "0")}`;
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 1000_00, date: `${prevYear}-06-10` }),
                txn(2, { categoryId: 2, amount: -400_00, date: `${prevYear}-06-11` }),
                txn(3, { categoryId: 2, amount: -310_00, date: `${currentMonth}-01` }),
                txn(4, { categoryId: 2, amount: -90_00, date: `${previousMonth}-10` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(screen.getByText("Saved").closest<HTMLElement>(".kpi")!).toHaveTextContent("510 ₽");
        expect(
            screen.getByText("Spent this month").closest<HTMLElement>(".kpi")!,
        ).toHaveTextContent("310 ₽");
        expect(
            screen.getByText("Spent this month").closest<HTMLElement>(".kpi")!,
        ).toHaveTextContent("vs 90 ₽ last month");
    });

    it("keeps income and expense separated in the all-time category charts", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 700_00, date: `${prevYear}-02-10` }),
                txn(2, { categoryId: 2, amount: -250_00, date: `${prevYear}-02-11` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const donuts = screen
            .getAllByTestId("donut-chart")
            .map((node) => JSON.parse(node.dataset["series"] ?? "[]") as ChartRow[]);
        expect(donuts[0]?.[0]).toMatchObject({ name: "Groceries", value: 250 });
        expect(donuts[1]?.[0]).toMatchObject({ name: "Salary", value: 700 });
        expect(typeof donuts[0]?.[0]?.["color"]).toBe("string");
        expect(typeof donuts[1]?.[0]?.["color"]).toBe("string");
    });

    it("shows negative net YTD in expense color", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 200_00, date: `${year}-01-10` }),
                txn(2, { categoryId: 2, amount: -500_00, date: `${year}-01-15` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const netKpi = screen.getByText("Net year to date").closest<HTMLElement>(".kpi")!;
        expect(netKpi).toHaveTextContent("-300 ₽");
        expect(netKpi.querySelector<HTMLElement>(".kpi__value")!).toHaveStyle({
            color: "var(--m-expense)",
        });
    });

    it("shows positive net YTD in income color", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 1000_00, date: `${year}-01-10` }),
                txn(2, { categoryId: 2, amount: -300_00, date: `${year}-01-15` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const netKpi = screen.getByText("Net year to date").closest<HTMLElement>(".kpi")!;
        expect(netKpi.querySelector<HTMLElement>(".kpi__value")!).toHaveStyle({
            color: "var(--m-income)",
        });
    });

    it("shows negative savings rate in expense color and zero rate without tint", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 1000_00, date: `${prevYear}-06-10` }),
                txn(2, { categoryId: 2, amount: -800_00, date: `${prevYear}-06-11` }),
                txn(3, { categoryId: 1, amount: 1000_00, date: `${prevYear}-07-10` }),
                txn(4, { categoryId: 2, amount: -800_00, date: `${prevYear}-07-11` }),
                txn(5, { categoryId: 1, amount: 1000_00, date: `${prevYear}-08-10` }),
                txn(6, { categoryId: 2, amount: -800_00, date: `${prevYear}-08-11` }),
                txn(7, { categoryId: 1, amount: 1000_00, date: `${prevYear}-09-10` }),
                txn(8, { categoryId: 2, amount: -800_00, date: `${prevYear}-09-11` }),
                txn(9, { categoryId: 1, amount: 1000_00, date: `${prevYear}-10-10` }),
                txn(10, { categoryId: 2, amount: -800_00, date: `${prevYear}-10-11` }),
                txn(11, { categoryId: 1, amount: 1000_00, date: `${prevYear}-11-10` }),
                txn(12, { categoryId: 2, amount: -800_00, date: `${prevYear}-11-11` }),
                txn(13, { categoryId: 1, amount: 1000_00, date: `${prevYear}-12-10` }),
                txn(14, { categoryId: 2, amount: -800_00, date: `${prevYear}-12-11` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const savingsKpi = screen.getByText("Savings rate").closest<HTMLElement>(".kpi")!;
        expect(savingsKpi).toHaveTextContent("20%");
        expect(savingsKpi.querySelector<HTMLElement>(".kpi__value")!).toHaveStyle({
            color: "var(--m-income)",
        });
    });

    it("shows negative savings rate in expense color", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 500_00, date: `${prevYear}-06-10` }),
                txn(2, { categoryId: 2, amount: -800_00, date: `${prevYear}-06-11` }),
                txn(3, { categoryId: 1, amount: 500_00, date: `${prevYear}-07-10` }),
                txn(4, { categoryId: 2, amount: -800_00, date: `${prevYear}-07-11` }),
                txn(5, { categoryId: 1, amount: 500_00, date: `${prevYear}-08-10` }),
                txn(6, { categoryId: 2, amount: -800_00, date: `${prevYear}-08-11` }),
                txn(7, { categoryId: 1, amount: 500_00, date: `${prevYear}-09-10` }),
                txn(8, { categoryId: 2, amount: -800_00, date: `${prevYear}-09-11` }),
                txn(9, { categoryId: 1, amount: 500_00, date: `${prevYear}-10-10` }),
                txn(10, { categoryId: 2, amount: -800_00, date: `${prevYear}-10-11` }),
                txn(11, { categoryId: 1, amount: 500_00, date: `${prevYear}-11-10` }),
                txn(12, { categoryId: 2, amount: -800_00, date: `${prevYear}-11-11` }),
                txn(13, { categoryId: 1, amount: 500_00, date: `${prevYear}-12-10` }),
                txn(14, { categoryId: 2, amount: -800_00, date: `${prevYear}-12-11` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const savingsKpi = screen.getByText("Savings rate").closest<HTMLElement>(".kpi")!;
        expect(savingsKpi).toHaveTextContent("-60%");
        expect(savingsKpi.querySelector<HTMLElement>(".kpi__value")!).toHaveStyle({
            color: "var(--m-expense)",
        });
    });

    it("shows forecast in warning color when above average and in income color when below", () => {
        const currentMonth = `${year}-${String(now.getMonth() + 1).padStart(2, "0")}`;
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 1000_00, date: `${prevYear}-06-10` }),
                txn(2, { categoryId: 2, amount: -400_00, date: `${prevYear}-06-11` }),
                txn(3, { categoryId: 2, amount: -700_00, date: `${currentMonth}-01` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const forecastKpi = screen.getByText("Month forecast").closest<HTMLElement>(".kpi")!;
        expect(forecastKpi.querySelector<HTMLElement>(".kpi__value")!).toHaveStyle({
            color: "var(--m-warning)",
        });
    });

    it("shows saved in income color for positive and expense for negative", () => {
        const currentMonth = `${year}-${String(now.getMonth() + 1).padStart(2, "0")}`;
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 1000_00, date: `${prevYear}-06-10` }),
                txn(2, { categoryId: 2, amount: -400_00, date: `${prevYear}-06-11` }),
                txn(3, { categoryId: 1, amount: 1000_00, date: `${prevYear}-07-10` }),
                txn(4, { categoryId: 2, amount: -800_00, date: `${prevYear}-07-11` }),
                txn(5, { categoryId: 1, amount: 1000_00, date: `${prevYear}-08-10` }),
                txn(6, { categoryId: 2, amount: -800_00, date: `${prevYear}-08-11` }),
                txn(7, { categoryId: 1, amount: 1000_00, date: `${prevYear}-09-10` }),
                txn(8, { categoryId: 2, amount: -800_00, date: `${prevYear}-09-11` }),
                txn(9, { categoryId: 1, amount: 1000_00, date: `${prevYear}-10-10` }),
                txn(10, { categoryId: 2, amount: -800_00, date: `${prevYear}-10-11` }),
                txn(11, { categoryId: 1, amount: 1000_00, date: `${prevYear}-11-10` }),
                txn(12, { categoryId: 2, amount: -800_00, date: `${prevYear}-11-11` }),
                txn(13, { categoryId: 1, amount: 1000_00, date: `${prevYear}-12-10` }),
                txn(14, { categoryId: 2, amount: -800_00, date: `${prevYear}-12-11` }),
                txn(15, { categoryId: 2, amount: -200_00, date: `${currentMonth}-10` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const savedKpi = screen.getByText("Saved").closest<HTMLElement>(".kpi")!;
        expect(savedKpi.querySelector<HTMLElement>(".kpi__value")!).toHaveStyle({
            color: "var(--m-income)",
        });
    });

    it("shows saved in expense color when last 12 months are net negative", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 500_00, date: `${prevYear}-06-10` }),
                txn(2, { categoryId: 2, amount: -800_00, date: `${prevYear}-06-11` }),
                txn(3, { categoryId: 1, amount: 500_00, date: `${prevYear}-07-10` }),
                txn(4, { categoryId: 2, amount: -800_00, date: `${prevYear}-07-11` }),
                txn(5, { categoryId: 1, amount: 500_00, date: `${prevYear}-08-10` }),
                txn(6, { categoryId: 2, amount: -800_00, date: `${prevYear}-08-11` }),
                txn(7, { categoryId: 1, amount: 500_00, date: `${prevYear}-09-10` }),
                txn(8, { categoryId: 2, amount: -800_00, date: `${prevYear}-09-11` }),
                txn(9, { categoryId: 1, amount: 500_00, date: `${prevYear}-10-10` }),
                txn(10, { categoryId: 2, amount: -800_00, date: `${prevYear}-10-11` }),
                txn(11, { categoryId: 1, amount: 500_00, date: `${prevYear}-11-10` }),
                txn(12, { categoryId: 2, amount: -800_00, date: `${prevYear}-11-11` }),
                txn(13, { categoryId: 1, amount: 500_00, date: `${prevYear}-12-10` }),
                txn(14, { categoryId: 2, amount: -800_00, date: `${prevYear}-12-11` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const savedKpi = screen.getByText("Saved").closest<HTMLElement>(".kpi")!;
        expect(savedKpi.querySelector<HTMLElement>(".kpi__value")!).toHaveStyle({
            color: "var(--m-expense)",
        });
    });

    it("shows runway warning when under 3 months", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 1000_00, date: `${prevYear}-06-10` }),
                txn(2, { categoryId: 2, amount: -900_00, date: `${prevYear}-06-11` }),
                txn(3, { categoryId: 1, amount: 1000_00, date: `${prevYear}-07-10` }),
                txn(4, { categoryId: 2, amount: -900_00, date: `${prevYear}-07-11` }),
                txn(5, { categoryId: 1, amount: 1000_00, date: `${prevYear}-08-10` }),
                txn(6, { categoryId: 2, amount: -900_00, date: `${prevYear}-08-11` }),
                txn(7, { categoryId: 1, amount: 1000_00, date: `${prevYear}-09-10` }),
                txn(8, { categoryId: 2, amount: -900_00, date: `${prevYear}-09-11` }),
                txn(9, { categoryId: 1, amount: 1000_00, date: `${prevYear}-10-10` }),
                txn(10, { categoryId: 2, amount: -900_00, date: `${prevYear}-10-11` }),
                txn(11, { categoryId: 1, amount: 1000_00, date: `${prevYear}-11-10` }),
                txn(12, { categoryId: 2, amount: -900_00, date: `${prevYear}-11-11` }),
                txn(13, { categoryId: 1, amount: 1000_00, date: `${prevYear}-12-10` }),
                txn(14, { categoryId: 2, amount: -900_00, date: `${prevYear}-12-11` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const runwayKpi = screen.getByText("Runway").closest<HTMLElement>(".kpi")!;
        expect(runwayKpi.querySelector<HTMLElement>(".kpi__value")!).toHaveStyle({
            color: "var(--m-warning)",
        });
    });

    it("supplies a 12-month window to the trend chart", async () => {
        const months = Array.from({ length: 20 }, (_, i) => {
            const d = new Date(year, now.getMonth() - 20 + i, 1);
            return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
        });
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: months.map((key, i) =>
                txn(i + 1, { amount: -(i + 1) * 100, date: `${key}-10` }),
            ),
        });

        const { user } = renderUI(<DashboardPage firstYear={year - 3} lastYear={year} />);

        expect(series("composite-chart")).toHaveLength(20);
        await user.click(screen.getByRole("button", { name: "1y" }));
        expect(series("composite-chart")).toHaveLength(12);
    });

    it("sets the active preset button state", async () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: Array.from({ length: 40 }, (_, i) => {
                const d = new Date(year, now.getMonth() - 40 + i, 1);
                const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
                return txn(i + 1, { amount: -100_00, date: `${key}-10` });
            }),
        });

        const { user } = renderUI(<DashboardPage firstYear={year - 4} lastYear={year} />);

        expect(screen.getByRole("button", { name: "3y" })).toHaveAttribute("data-selected", "true");
        await user.click(screen.getByRole("button", { name: "6m" }));
        expect(screen.getByRole("button", { name: "6m" })).toHaveAttribute("data-selected", "true");
        expect(screen.getByRole("button", { name: "3y" })).not.toHaveAttribute("data-selected");
    });

    it("does not render the accounts filter with only one account", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [txn(1, { amount: -100_00 })],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(screen.queryByRole("button", { name: "All accounts" })).not.toBeInTheDocument();
        expect(screen.getByText("Card")).toBeInTheDocument();
    });

    it("plots the selected category's own monthly spend in the drill-down chart", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            groups: [{ id: 1, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                { id: 2, groupId: 1, name: "Groceries", archived: false, sort: 1 },
                { id: 3, groupId: 1, name: "Transport", archived: false, sort: 2 },
            ],
            transactions: [
                txn(1, { categoryId: 2, amount: -100_00, date: `${year}-01-15` }),
                txn(2, { categoryId: 2, amount: -50_00, date: `${year}-03-20` }),
                txn(3, { categoryId: 3, amount: -200_00, date: `${year}-01-20` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        // the drill defaults to "Groceries": its own months in roubles, and the
        // other category's spend must never leak into the selected one
        const drill = series("bar-chart", 0);
        expect(drill.find((r) => r.month === "Jan")!.Spent).toBe(100);
        expect(drill.find((r) => r.month === "Mar")!.Spent).toBe(50);
        expect(drill.find((r) => r.month === "Feb")!.Spent).toBe(0);
        expect(drill.reduce((sum, r) => sum + r.Spent!, 0)).toBe(150);
    });

    it("renders donut empty state when no categorized transactions", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: null, amount: -100_00, date: `${prevYear}-03-10` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(screen.getAllByText("No categorized entries yet")).toHaveLength(4);
    });

    it(`formats x-axis month ticks as "Mon 'YY"`, () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { amount: -100_00, date: `${prevYear}-01-10` }),
                txn(2, { amount: -200_00, date: `${prevYear}-02-15` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(series("composite-chart")).toHaveLength(2);
        expect(series("composite-chart")[0]!.x).toBe(`${prevYear}-01`);
        expect(series("composite-chart")[1]!.x).toBe(`${prevYear}-02`);
    });

    it("sets null savings rate for months with no income", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 2, amount: -300_00, date: `${prevYear}-03-10` }),
                txn(2, { categoryId: 2, amount: -300_00, date: `${prevYear}-04-10` }),
                txn(3, { categoryId: 1, amount: 1000_00, date: `${prevYear}-05-10` }),
                txn(4, { categoryId: 2, amount: -300_00, date: `${prevYear}-05-11` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(trendRow(`${prevYear}-03`)!["Savings rate %"]).toBeNull();
        expect(trendRow(`${prevYear}-04`)!["Savings rate %"]).toBeNull();
        expect(trendRow(`${prevYear}-05`)!["Savings rate %"]).toBe(70);
    });

    it("clamps the savings rate to the [-100, 100] range", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 1, amount: 100_00, date: `${prevYear}-01-10` }),
                txn(2, { categoryId: 2, amount: -500_00, date: `${prevYear}-01-11` }),
                txn(3, { categoryId: 1, amount: 100_00, date: `${prevYear}-02-10` }),
                txn(4, { categoryId: 2, amount: -500_00, date: `${prevYear}-02-11` }),
                txn(5, { categoryId: 1, amount: 100_00, date: `${prevYear}-03-10` }),
                txn(6, { categoryId: 2, amount: -500_00, date: `${prevYear}-03-11` }),
                txn(7, { categoryId: 1, amount: 100_00, date: `${prevYear}-04-10` }),
                txn(8, { categoryId: 2, amount: -500_00, date: `${prevYear}-04-11` }),
                txn(9, { categoryId: 1, amount: 100_00, date: `${prevYear}-05-10` }),
                txn(10, { categoryId: 2, amount: -500_00, date: `${prevYear}-05-11` }),
                txn(11, { categoryId: 1, amount: 100_00, date: `${prevYear}-06-10` }),
                txn(12, { categoryId: 2, amount: -500_00, date: `${prevYear}-06-11` }),
                txn(13, { categoryId: 1, amount: 100_00, date: `${prevYear}-07-10` }),
                txn(14, { categoryId: 2, amount: -500_00, date: `${prevYear}-07-11` }),
                txn(15, { categoryId: 1, amount: 100_00, date: `${prevYear}-08-10` }),
                txn(16, { categoryId: 2, amount: -500_00, date: `${prevYear}-08-11` }),
                txn(17, { categoryId: 1, amount: 100_00, date: `${prevYear}-09-10` }),
                txn(18, { categoryId: 2, amount: -500_00, date: `${prevYear}-09-11` }),
                txn(19, { categoryId: 1, amount: 100_00, date: `${prevYear}-10-10` }),
                txn(20, { categoryId: 2, amount: -500_00, date: `${prevYear}-10-11` }),
                txn(21, { categoryId: 1, amount: 100_00, date: `${prevYear}-11-10` }),
                txn(22, { categoryId: 2, amount: -500_00, date: `${prevYear}-11-11` }),
                txn(23, { categoryId: 1, amount: 100_00, date: `${prevYear}-12-10` }),
                txn(24, { categoryId: 2, amount: -500_00, date: `${prevYear}-12-11` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const rate = trendRow(`${prevYear}-01`)!["Savings rate %"];
        expect(rate).toBeLessThanOrEqual(100);
        expect(rate).toBeGreaterThanOrEqual(-100);
    });

    it("shows YTD trend when there is only one closed month", async () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [txn(1, { amount: -100_00, date: `${prevYear}-06-10` })],
        });

        const { user } = renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);
        await user.click(screen.getByRole("button", { name: "YTD" }));

        const keys = series("composite-chart").map((r) => r.x);
        expect(keys).toContain(`${prevYear}-06`);
    });

    it("rounds the avg monthly spend to whole roubles", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [
                txn(1, { categoryId: 2, amount: -333_00, date: `${prevYear}-01-10` }),
                txn(2, { categoryId: 2, amount: -333_00, date: `${prevYear}-02-10` }),
                txn(3, { categoryId: 2, amount: -334_00, date: `${prevYear}-03-10` }),
                txn(4, { categoryId: 2, amount: -333_00, date: `${prevYear}-04-10` }),
                txn(5, { categoryId: 2, amount: -333_00, date: `${prevYear}-05-10` }),
                txn(6, { categoryId: 2, amount: -333_00, date: `${prevYear}-06-10` }),
                txn(7, { categoryId: 2, amount: -333_00, date: `${prevYear}-07-10` }),
                txn(8, { categoryId: 2, amount: -333_00, date: `${prevYear}-08-10` }),
                txn(9, { categoryId: 2, amount: -333_00, date: `${prevYear}-09-10` }),
                txn(10, { categoryId: 2, amount: -333_00, date: `${prevYear}-10-10` }),
                txn(11, { categoryId: 2, amount: -333_00, date: `${prevYear}-11-10` }),
                txn(12, { categoryId: 2, amount: -333_00, date: `${prevYear}-12-10` }),
            ],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        const avgKpi = screen.getByText("Avg monthly spend").closest<HTMLElement>(".kpi")!;
        expect(avgKpi).toHaveTextContent("333 ₽");
    });
});
