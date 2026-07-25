import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
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

    it("edits a monthly budget cell and opens the category delete form", async () => {
        const setBudget = vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
        const { user } = renderUI(<BudgetPage results={new Map([[2026, result()]])} firstYear={2026} lastYear={2026} />);
        await user.click(screen.getByText("Month"));
        const food = screen.getByText("Groceries").closest("tr");
        await user.click(food.querySelector(".budget-cell"));
        const input = food.querySelector(".budget-cell__input");
        await user.clear(input);
        await user.type(input, "300");
        await user.keyboard("{Enter}");
        await waitFor(() => expect(setBudget).toHaveBeenCalledWith(2, 2026, expect.any(Number), 30000));

        await user.click(food.querySelector(".cat-row__menu button"));
        await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("Delete Groceries");
    });
});
