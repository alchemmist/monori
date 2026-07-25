import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@mantine/charts", () => ({
    AreaChart: ({ data }) => <div data-testid="area-chart">{data.length} points</div>,
    BarChart: ({ data }) => <div data-testid="bar-chart">{data.length} points</div>,
    CompositeChart: ({ data }) => <div data-testid="composite-chart">{data.length} points</div>,
    DonutChart: ({ data }) => <div data-testid="donut-chart">{data.map((d) => d.name).join(",")}</div>,
}));

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
const month = String(now.getMonth() + 1).padStart(2, "0");

describe("DashboardPage", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders balances, calculated KPI cards and every dashboard chart", () => {
        seed({
            accounts: [
                { id: 1, name: "Card", type: "card", icon: "card", color: "#000", openingBalance: 10000 },
                { id: 2, name: "Cash", type: "cash", icon: "cash", color: "#000", openingBalance: 0 },
            ],
            transactions: [
                { id: 1, accountId: 1, categoryId: 1, amount: 100000, date: `${year}-01-10` },
                { id: 2, accountId: 1, categoryId: 2, amount: -25000, date: `${year}-02-10` },
                { id: 3, accountId: 2, categoryId: 3, amount: -10000, date: `${year}-${month}-10` },
            ],
        });

        renderUI(<DashboardPage firstYear={year - 1} lastYear={year} />);

        expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
        expect(screen.getByText("Card")).toBeInTheDocument();
        expect(screen.getByText("Cash")).toBeInTheDocument();
        expect(screen.getByText("Net year to date")).toBeInTheDocument();
        expect(screen.getByText("Savings rate")).toBeInTheDocument();
        expect(screen.getByText("Income vs expenses", { exact: false })).toBeInTheDocument();
        expect(screen.getByText("Spending by category")).toBeInTheDocument();
        expect(screen.getByText("Category by month")).toBeInTheDocument();
        expect(screen.getByText("Cumulative net · all time")).toBeInTheDocument();
        expect(screen.getAllByTestId("bar-chart").length).toBeGreaterThanOrEqual(3);
        expect(screen.getByTestId("donut-chart")).toHaveTextContent("Groceries,Rent");
    });

    it("filters charts by account and changes the trend range through controls", async () => {
        seed({ accounts: [
            { id: 1, name: "Card", type: "card", icon: "card", color: "#000", openingBalance: 0 },
            { id: 2, name: "Cash", type: "cash", icon: "cash", color: "#000", openingBalance: 0 },
        ] });
        const { user } = renderUI(
            <DashboardPage firstYear={year - 1} lastYear={year} />,
        );
        await user.click(screen.getByRole("button", { name: "All accounts" }));
        await user.click(document.querySelector('[role="option"][value="1"]'));
        await user.click(screen.getByRole("button", { name: "All" }));
        await user.click(screen.getByRole("button", { name: /navigator/ }));
        expect(screen.getByRole("button", { name: "Card" })).toBeInTheDocument();
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
        expect(screen.getByText("—")).toBeInTheDocument();
        expect(screen.getByTestId("donut-chart")).toHaveTextContent("");
    });

    it("groups spending after the first eleven categories into Other", () => {
        const categories = Array.from({ length: 12 }, (_, i) => ({
            id: i + 10, groupId: 2, name: `Expense ${i + 1}`,
        }));
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense" }],
            categories,
            transactions: categories.map((c, i) => ({
                id: c.id, accountId: 1, categoryId: c.id, amount: -(i + 1) * 100,
                date: `${year}-02-10`,
            })),
        });
        renderUI(<DashboardPage firstYear={year} lastYear={year} />);
        expect(screen.getByTestId("donut-chart")).toHaveTextContent("Other");
    });
});
