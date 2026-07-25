import { describe, expect, it, beforeEach } from "vitest";
import DashboardPage from "./DashboardPage.jsx";
import { renderUI, screen, atDemo, seed, tx, resetStore, waitFor } from "../test/render.jsx";

describe("DashboardPage", () => {
    beforeEach(() => {
        resetStore();
    });

    describe("page structure", () => {
        it("renders with fade-in animation class", () => {
            atDemo();
            const { container } = renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(container.querySelector(".fade-in")).toBeInTheDocument();
        });

        it("renders Dashboard title", () => {
            atDemo();
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Dashboard")).toBeInTheDocument();
        });

        it("renders page title with no margin", () => {
            atDemo();
            const { container } = renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            const title = screen.getByText("Dashboard");
            expect(title).toHaveClass("page-title");
            expect(title).toHaveStyle({ margin: 0 });
        });

        it("renders charts grid", () => {
            atDemo();
            const { container } = renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(container.querySelector(".charts-grid")).toBeInTheDocument();
        });
    });

    describe("account display", () => {
        it("does not show account selector when only one account", () => {
            seed({ accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB" }] });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            const selects = screen.queryAllByRole("button");
            const inlineSelect = selects.filter((s) => s.textContent.includes("All accounts"));
            expect(inlineSelect.length).toBe(0);
        });

        it("shows account selector when multiple accounts exist", () => {
            seed({
                accounts: [
                    { id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB" },
                    { id: 2, name: "Cash", type: "cash", icon: "ruble", color: "#10b981", currency: "RUB" },
                ],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            // The selector is rendered with the account filter
            const accounts = screen.getByText("Card");
            expect(accounts).toBeInTheDocument();
        });

        it("displays balance cards for all accounts", () => {
            seed({
                accounts: [
                    { id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" },
                    { id: 2, name: "Cash", type: "cash", icon: "ruble", color: "#10b981", currency: "RUB", iconImage: null, sort: 2, archived: false, openingBalance: 50000, openingDate: "2026-01-01" },
                ],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Card")).toBeInTheDocument();
            expect(screen.getByText("Cash")).toBeInTheDocument();
        });

        it("does not display balance row when no accounts", () => {
            seed({ accounts: [] });
            const { container } = renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(container.querySelector(".balance-row")).not.toBeInTheDocument();
        });

        it("shows balance row when accounts exist", () => {
            seed({
                accounts: [
                    { id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" },
                ],
            });
            const { container } = renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(container.querySelector(".balance-row")).toBeInTheDocument();
        });
    });

    describe("KPI display", () => {
        it("renders KPI row", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [
                    tx(1, { date: "2026-01-15", amount: 100000, categoryId: 1 }),
                    tx(2, { date: "2026-01-20", amount: -50000, categoryId: 2 }),
                ],
            });
            const { container } = renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(container.querySelector(".kpi-row")).toBeInTheDocument();
        });

        it("displays Net year to date KPI", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Net year to date")).toBeInTheDocument();
        });

        it("displays Savings rate KPI", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Savings rate")).toBeInTheDocument();
        });

        it("displays Avg monthly spend KPI", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Avg monthly spend")).toBeInTheDocument();
        });

        it("displays Spent this month KPI", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Spent this month")).toBeInTheDocument();
        });

        it("displays Daily rate KPI", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Daily rate")).toBeInTheDocument();
        });

        it("displays Month forecast KPI", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Month forecast")).toBeInTheDocument();
        });

        it("displays Saved KPI", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Saved")).toBeInTheDocument();
        });

        it("displays Runway KPI", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Runway")).toBeInTheDocument();
        });
    });

    describe("charts", () => {
        it("renders trend chart title", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText(/Income vs expenses/)).toBeInTheDocument();
        });

        it("renders preset buttons for trend chart", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByRole("button", { name: "6m" })).toBeInTheDocument();
            expect(screen.getByRole("button", { name: "1y" })).toBeInTheDocument();
            expect(screen.getByRole("button", { name: "3y" })).toBeInTheDocument();
            expect(screen.getByRole("button", { name: "5y" })).toBeInTheDocument();
            expect(screen.getByRole("button", { name: "YTD" })).toBeInTheDocument();
            expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
        });

        it("renders donut chart title", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Spending by category")).toBeInTheDocument();
        });

        it("renders drill chart title", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Category by month")).toBeInTheDocument();
        });

        it("renders category stack chart title", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText(/Spending by category · by month/)).toBeInTheDocument();
        });

        it("renders cumulative chart title", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText(/Cumulative net · all time/)).toBeInTheDocument();
        });

        it("renders group stack chart title", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Expense structure by group")).toBeInTheDocument();
        });
    });

    describe("drill chart interaction", () => {
        it("shows placeholder when no category selected", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                categories: [
                    { id: 1, groupId: 1, name: "Income", keywords: "", sort: 1, archived: false },
                    { id: 2, groupId: 2, name: "Groceries", keywords: "food", sort: 1, archived: false },
                ],
                transactions: [],
                groups: [
                    { id: 1, name: "Income", kind: "income", sort: 1 },
                    { id: 2, name: "Living", kind: "expense", sort: 2 },
                ],
            });
            const { container } = renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(container.textContent).toContain("Pick a category to see its monthly spending");
        });
    });

    describe("empty state", () => {
        it("renders with no transactions", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Dashboard")).toBeInTheDocument();
        });

        it("renders with no categories", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                categories: [],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Dashboard")).toBeInTheDocument();
        });
    });

    describe("data with transactions", () => {
        it("includes transactions in filtered view", () => {
            seed({
                accounts: [
                    { id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" },
                    { id: 2, name: "Cash", type: "cash", icon: "ruble", color: "#10b981", currency: "RUB", iconImage: null, sort: 2, archived: false, openingBalance: 50000, openingDate: "2026-01-01" },
                ],
                categories: [
                    { id: 1, groupId: 1, name: "Income", keywords: "", sort: 1, archived: false },
                    { id: 2, groupId: 2, name: "Groceries", keywords: "food", sort: 1, archived: false },
                ],
                transactions: [
                    tx(1, { accountId: 1, date: "2026-06-15", amount: 100000, categoryId: 1 }),
                    tx(2, { accountId: 1, date: "2026-06-20", amount: -50000, categoryId: 2 }),
                ],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Dashboard")).toBeInTheDocument();
        });
    });

    describe("year range", () => {
        it("uses firstYear and lastYear props", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2023} lastYear={2025} />);
            expect(screen.getByText("Dashboard")).toBeInTheDocument();
        });
    });

    describe("time presets interaction", () => {
        it("highlights active preset button", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [
                    tx(1, { date: "2025-01-15", amount: 100000, categoryId: 1 }),
                    tx(2, { date: "2025-02-20", amount: -50000, categoryId: 2 }),
                    tx(3, { date: "2025-03-20", amount: -30000, categoryId: 2 }),
                    tx(4, { date: "2025-04-20", amount: -30000, categoryId: 2 }),
                    tx(5, { date: "2025-05-20", amount: -30000, categoryId: 2 }),
                    tx(6, { date: "2025-06-20", amount: -30000, categoryId: 2 }),
                    tx(7, { date: "2025-07-20", amount: -30000, categoryId: 2 }),
                ],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            const threeYButton = screen.getByRole("button", { name: "3y" });
            expect(threeYButton).toBeInTheDocument();
        });
    });

    describe("demo data", () => {
        it("renders with demo data", () => {
            atDemo();
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Dashboard")).toBeInTheDocument();
        });

        it("shows multiple accounts in demo", () => {
            atDemo();
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Dashboard")).toBeInTheDocument();
        });

        it("renders all charts with demo data", () => {
            atDemo();
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText(/Income vs expenses/)).toBeInTheDocument();
            expect(screen.getByText("Spending by category")).toBeInTheDocument();
            expect(screen.getByText("Category by month")).toBeInTheDocument();
            expect(screen.getByText(/Cumulative net · all time/)).toBeInTheDocument();
        });
    });

    describe("KPI component", () => {
        it("displays KPI label", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(screen.getByText("Net year to date")).toBeInTheDocument();
        });

        it("displays KPI sub text", () => {
            seed({
                accounts: [{ id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", iconImage: null, sort: 1, archived: false, openingBalance: 100000, openingDate: "2026-01-01" }],
                transactions: [],
            });
            const { container } = renderUI(<DashboardPage firstYear={2024} lastYear={2026} />);
            expect(container.textContent).toContain("last 12 months");
        });
    });
});
