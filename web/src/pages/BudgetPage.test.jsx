import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderUI, resetStore, screen, seed } from "../test/render.jsx";
import BudgetPage from "./BudgetPage.jsx";

const result = () => ({
    available: Array(12).fill(10000), overspent: Array(12).fill(-500), income: Array(12).fill(50000), budgetedTotal: Array(12).fill(20000),
    byCategory: new Map([[2, Array.from({ length: 12 }, () => ({ budgeted: 20000, outflows: -5000, balance: 15000 }))]]),
});

describe("BudgetPage", () => {
    beforeEach(() => { resetStore(); seed(); });
    it("renders the full year grid with expense categories", () => {
        renderUI(<BudgetPage results={new Map([[2026, result()]])} firstYear={2026} lastYear={2026} />);
        expect(screen.getByRole("heading", { name: "Budget" })).toBeInTheDocument();
        expect(screen.getByText("Groceries")).toBeInTheDocument();
        expect(screen.getByText("Rent")).toBeInTheDocument();
    });
    it("switches to month mode, expands group data and opens new category", async () => {
        const { user } = renderUI(<BudgetPage results={new Map([[2026, result()]])} firstYear={2026} lastYear={2026} />);
        await user.click(screen.getByText("Month"));
        expect(screen.getByText("Available to budget")).toBeInTheDocument();
        expect(screen.getByText("Income")).toBeInTheDocument();
        await user.click(screen.getByText("Living"));
        expect(screen.queryByText("Groceries")).not.toBeInTheDocument();
        await user.click(screen.getByLabelText("Add category"));
        expect(screen.getByText("New category")).toBeInTheDocument();
    });
    it("changes the density of year columns", async () => {
        const { user } = renderUI(<BudgetPage results={new Map([[2026, result()]])} firstYear={2026} lastYear={2026} />);
        await user.click(screen.getByText("Plan"));
        expect(document.querySelectorAll(".yg-metric")).toHaveLength(12);
    });
});
