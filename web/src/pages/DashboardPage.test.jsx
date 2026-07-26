import { beforeEach, describe, expect, it, vi } from "vitest";

// The real charts render an SVG we cannot read numbers out of, so each one is
// swapped for a node that serialises the exact rows the page computed. That
// makes every aggregation — buckets, totals, per-account filtering — assertable.
vi.mock("@mantine/charts", () => {
    const serialize = (testid) =>
        function Chart({ data }) {
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
    default: ({ items, range, onChange }) => (
        <button type="button" onClick={() => onChange([0, Math.max(0, items.length - 1)])}>
            navigator {range.join("-")}
        </button>
    ),
}));

import DashboardPage from "./DashboardPage.jsx";
import { renderUI, resetStore, screen, seed } from "../test/render.jsx";

const now = new Date();
const year = now.getFullYear();
const prevYear = year - 1;

/** Rows a mocked chart was handed, parsed back out of its `data-series`. */
function series(testid, index = 0) {
    const nodes = screen.getAllByTestId(testid);
    return JSON.parse(nodes[index].dataset.series);
}

/** The composite trend chart's row for a 'YYYY-MM' month key. */
function trendRow(key) {
    return series("composite-chart").find((r) => r.x === key);
}

const account = (id, name, openingBalance) => ({
    id,
    name,
    type: "card",
    icon: "card",
    color: "#000",
    openingBalance,
});

const txn = (id, patch) => ({
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

        const balance = (name) =>
            screen.getByText(name).closest(".balance-card").querySelector(".balance-card__value")
                .textContent;
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

        const kpi = screen.getByText("Net year to date").closest(".kpi");
        expect(kpi.querySelector(".kpi__value")).toHaveTextContent("500 ₽");
        expect(kpi.querySelector(".kpi__sub")).toHaveTextContent(String(year));
    });

    it("keeps savings rate at zero and calculates negative runway when closed history has spending but no income", () => {
        seed({
            accounts: [account(1, "Card", 0)],
            transactions: [txn(1, { categoryId: 2, amount: -300_00, date: `${prevYear}-03-10` })],
        });

        renderUI(<DashboardPage firstYear={prevYear} lastYear={year} />);

        expect(screen.getByText("Savings rate").closest(".kpi")).toHaveTextContent("0%");
        expect(screen.getByText("Runway").closest(".kpi")).toHaveTextContent("-1.0 mo");
        expect(trendRow(`${prevYear}-03`)["Savings rate %"]).toBeNull();
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

        expect(trendRow(`${prevYear}-04`).Expenses).toBe(900);

        await user.click(screen.getByRole("button", { name: "All accounts" }));
        await user.click(document.querySelector('[role="option"][value="1"]'));

        expect(screen.getByRole("button", { name: "Card" })).toBeInTheDocument();
        expect(trendRow(`${prevYear}-04`).Expenses).toBe(700);
        expect(series("donut-chart")).toEqual([]); // the donut year defaults to now
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
        expect(trendRow(months[0])).toBeUndefined();

        await user.click(screen.getByRole("button", { name: "All" }));

        expect(series("composite-chart")).toHaveLength(40);
        expect(trendRow(months[0]).Expenses).toBe(1);
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
        expect(screen.getByText("Runway").closest(".kpi")).toHaveTextContent("—");
        expect(series("donut-chart")).toEqual([]);
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
        expect(screen.getByText("Spent this month").closest(".kpi")).toHaveTextContent("250 ₽");
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

        const groups = series("bar-chart", 2);
        expect(groups.find((row) => row.month === "Feb")).toEqual({ month: "Feb", g2: 120, g3: 450 });
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
        expect(drill.find((row) => row.month === "Jan").Spent).toBe(200);
        expect(drill.find((row) => row.month === "Feb").Spent).toBe(90);
        expect(drill.find((row) => row.month === "Mar").Spent).toBe(0);
    });
});
