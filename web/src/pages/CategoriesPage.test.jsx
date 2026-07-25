import { describe, expect, it, vi, beforeEach } from "vitest";
import CategoriesPage from "./CategoriesPage.jsx";
import {
    renderUI,
    resetStore,
    atDemo,
    seed,
    screen,
    within,
    waitFor,
} from "../test/render.jsx";
import { useStore } from "../store.js";

describe("CategoriesPage", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders empty state with no groups", () => {
        seed({ groups: [], categories: [] });
        renderUI(<CategoriesPage />);

        expect(screen.getByRole("heading", { name: "Categories" })).toBeInTheDocument();
    });

    it("renders groups from seed data", () => {
        seed();
        renderUI(<CategoriesPage />);

        expect(screen.getByText("Income")).toBeInTheDocument();
        expect(screen.getByText("Living")).toBeInTheDocument();
    });

    it("shows page title", () => {
        seed();
        renderUI(<CategoriesPage />);

        expect(screen.getByRole("heading", { name: "Categories" })).toBeInTheDocument();
    });

    it("disables new category button when no groups exist", () => {
        seed({ groups: [], categories: [] });
        renderUI(<CategoriesPage />);

        expect(screen.getByRole("button", { name: "New category" })).toBeDisabled();
    });

    it("enables new category button when groups exist", () => {
        seed();
        renderUI(<CategoriesPage />);

        expect(screen.getByRole("button", { name: "New category" })).not.toBeDisabled();
    });

    it("shows transaction count for each category", () => {
        seed({
            transactions: [
                { id: 1, categoryId: 2, accountId: 1, date: "2026-01-01", amount: -1000 },
                { id: 2, categoryId: 2, accountId: 1, date: "2026-01-02", amount: -2000 },
                { id: 3, categoryId: 3, accountId: 1, date: "2026-01-03", amount: -3000 },
            ],
        });
        renderUI(<CategoriesPage />);

        const groceriesCard = screen.getByText("Groceries").closest(".kb-card");
        expect(within(groceriesCard).getByText("2")).toBeInTheDocument();

        const rentCard = screen.getByText("Rent").closest(".kb-card");
        expect(within(rentCard).getByText("1")).toBeInTheDocument();
    });

    it("shows archived badge on archived categories", () => {
        seed({
            categories: [
                { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
                { id: 2, groupId: 2, name: "Old Expense", keywords: "", sort: 1, archived: true },
            ],
        });
        renderUI(<CategoriesPage />);

        expect(screen.getByText("arch")).toBeInTheDocument();
    });

    it("shows keywords for categories that have them", () => {
        seed({
            categories: [
                { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
                {
                    id: 2,
                    groupId: 2,
                    name: "Groceries",
                    keywords: "food|market|grocery",
                    sort: 1,
                    archived: false,
                },
            ],
        });
        renderUI(<CategoriesPage />);

        const groceriesCard = screen.getByText("Groceries").closest(".kb-card");
        expect(within(groceriesCard).getByText("food, market, grocery")).toBeInTheDocument();
    });

    it("shows group kind tag (income/expense)", () => {
        seed();
        renderUI(<CategoriesPage />);

        expect(screen.getByText("income")).toBeInTheDocument();
        expect(screen.getAllByText("expense").length).toBeGreaterThan(0);
    });

    it("opens category edit dialog on new category button click", async () => {
        seed();
        const { user } = renderUI(<CategoriesPage />);

        await user.click(screen.getByRole("button", { name: "New category" }));

        expect(screen.getByRole("heading", { name: "New category" })).toBeInTheDocument();
    });

    it("opens category edit dialog on Add category button in group", async () => {
        seed();
        const { user } = renderUI(<CategoriesPage />);

        const addButtons = screen.getAllByText("Add category");
        await user.click(addButtons[0]);

        expect(screen.getByRole("heading", { name: "New category" })).toBeInTheDocument();
    });

    it("closes dialog when cancel is clicked", async () => {
        seed();
        const { user } = renderUI(<CategoriesPage />);

        await user.click(screen.getByRole("button", { name: "New category" }));

        expect(screen.getByRole("heading", { name: "New category" })).toBeInTheDocument();

        const cancelBtn = screen.getByRole("button", { name: "Cancel" });
        await user.click(cancelBtn);

        expect(
            screen.queryByRole("heading", { name: "New category" }),
        ).not.toBeInTheDocument();
    });

    it("renders groups in their sorted order", () => {
        seed({
            groups: [
                { id: 3, name: "Lifestyle", kind: "expense", sort: 3 },
                { id: 1, name: "Income", kind: "income", sort: 1 },
                { id: 2, name: "Living", kind: "expense", sort: 2 },
            ],
        });
        renderUI(<CategoriesPage />);

        const income = screen.getByText("Income");
        const living = screen.getByText("Living");
        const lifestyle = screen.getByText("Lifestyle");

        // Check that Income comes before Living which comes before Lifestyle
        expect(income.compareDocumentPosition(living) & 4).toBe(4);
        expect(living.compareDocumentPosition(lifestyle) & 4).toBe(4);
    });

    it("renders categories within each group in sorted order", () => {
        seed({
            categories: [
                { id: 3, groupId: 2, name: "Utilities", keywords: "", sort: 3, archived: false },
                { id: 1, groupId: 2, name: "Rent", keywords: "", sort: 1, archived: false },
                { id: 2, groupId: 2, name: "Internet", keywords: "", sort: 2, archived: false },
            ],
        });
        renderUI(<CategoriesPage />);

        const rent = screen.getByText("Rent");
        const internet = screen.getByText("Internet");
        const utilities = screen.getByText("Utilities");

        expect(rent.compareDocumentPosition(internet) & 4).toBe(4);
        expect(internet.compareDocumentPosition(utilities) & 4).toBe(4);
    });

    it("handles categories with no transactions gracefully", () => {
        seed({ transactions: [] });
        renderUI(<CategoriesPage />);

        expect(screen.getByText("Salary")).toBeInTheDocument();
        expect(screen.getByText("Groceries")).toBeInTheDocument();
    });

    it("shows income and expense options for new group", async () => {
        seed();
        const { user } = renderUI(<CategoriesPage />);

        const newGroupBtn = screen.getByRole("button", { name: /New group/i });
        await user.click(newGroupBtn);

        expect(screen.getByRole("button", { name: /Income group/i })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Expense group/i })).toBeInTheDocument();
    });

    it("correctly counts uncategorized transactions", () => {
        seed({
            transactions: [
                { id: 1, categoryId: 2, accountId: 1, date: "2026-01-01", amount: -1000 },
                { id: 2, categoryId: null, accountId: 1, date: "2026-01-02", amount: -2000 },
            ],
        });
        renderUI(<CategoriesPage />);

        const groceriesCard = screen.getByText("Groceries").closest(".kb-card");
        expect(within(groceriesCard).getByText("1")).toBeInTheDocument();
    });

    it("passes correct group data when opening create dialog", async () => {
        seed({
            groups: [
                { id: 1, name: "Income", kind: "income", sort: 1 },
                { id: 2, name: "Living", kind: "expense", sort: 2 },
            ],
        });
        renderUI(<CategoriesPage />);

        expect(screen.getByText("Income")).toBeInTheDocument();
        expect(screen.getByText("Living")).toBeInTheDocument();
    });

    it("renders groups with category count badges", () => {
        seed({
            categories: [
                { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
                { id: 2, groupId: 1, name: "Freelance", keywords: "", sort: 2, archived: false },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 1, archived: false },
            ],
        });
        renderUI(<CategoriesPage />);

        const incomeHead = screen.getByText("Income").closest(".kb-col__head");
        expect(within(incomeHead).getByText("2")).toBeInTheDocument();

        const livingHead = screen.getByText("Living").closest(".kb-col__head");
        expect(within(livingHead).getByText("1")).toBeInTheDocument();
    });

    it("shows income group creation with correct kind", async () => {
        seed();
        const { user } = renderUI(<CategoriesPage />);

        const newGroupBtn = screen.getByRole("button", { name: /New group/i });
        await user.click(newGroupBtn);

        const incomeBtn = screen.getByRole("button", { name: /Income group/i });
        await user.click(incomeBtn);

        expect(screen.getByRole("heading", { name: "New group" })).toBeInTheDocument();
        expect(screen.getByRole("radio", { name: "Income" })).toBeChecked();
    });

    it("shows expense group creation with correct kind", async () => {
        seed();
        const { user } = renderUI(<CategoriesPage />);

        const newGroupBtn = screen.getByRole("button", { name: /New group/i });
        await user.click(newGroupBtn);

        const expenseBtn = screen.getByRole("button", { name: /Expense group/i });
        await user.click(expenseBtn);

        expect(screen.getByRole("heading", { name: "New group" })).toBeInTheDocument();
        expect(screen.getByRole("radio", { name: "Expense" })).toBeChecked();
    });

    it("shows all categories within their groups", () => {
        seed();
        renderUI(<CategoriesPage />);

        // Income group should show Salary
        const incomeCol = screen.getByText("Income").closest(".kb-col");
        expect(within(incomeCol).getByText("Salary")).toBeInTheDocument();

        // Living group should show Groceries and Rent
        const livingCol = screen.getByText("Living").closest(".kb-col");
        expect(within(livingCol).getByText("Groceries")).toBeInTheDocument();
        expect(within(livingCol).getByText("Rent")).toBeInTheDocument();
    });

    it("renders with demo data successfully", () => {
        atDemo();
        renderUI(<CategoriesPage />);

        expect(screen.getByText("Income")).toBeInTheDocument();
        expect(screen.getByText("Fixed expenses")).toBeInTheDocument();
        expect(screen.getByText("Salary")).toBeInTheDocument();
    });
});
