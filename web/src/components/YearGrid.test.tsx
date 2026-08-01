import { describe, expect, it, vi } from "vitest";
import { renderUI, screen, within } from "../test/render.jsx";
import YearGrid from "./YearGrid.jsx";
import type { ComponentProps } from "react";
import type { BudgetMonth } from "../engine/budget.js";

const year = 2026;
const emptyMonths = (): BudgetMonth[] =>
    Array.from({ length: 12 }, () => ({ budgeted: 0, outflows: 0, balance: 0 }));

function renderGrid({
    first,
    second,
}: { first?: Partial<BudgetMonth>; second?: Partial<BudgetMonth> } = {}) {
    const groceries = emptyMonths();
    const rent = emptyMonths();
    Object.assign(
        groceries[0]!,
        first ?? { budgeted: 1_000_00, outflows: -500_00, balance: 500_00 },
    );
    Object.assign(rent[0]!, second ?? { budgeted: 200_00, outflows: -300_00, balance: -100_00 });
    const res = {
        year,
        available: Array.from({ length: 12 }, (): number => 0),
        overspent: Array.from({ length: 12 }, (): number => 0),
        income: Array.from({ length: 12 }, (): number => 0),
        budgetedTotal: Array.from({ length: 12 }, (): number => 0),
        byCategory: new Map([
            [2, groceries],
            [3, rent],
        ]),
    };
    const props = {
        res,
        prevRes: null,
        groups: [{ id: 7, name: "Home", kind: "expense", sort: 0 }],
        catsByGroup: new Map([
            [
                7,
                [
                    {
                        id: 2,
                        groupId: 7,
                        name: "Groceries",
                        keywords: "",
                        archived: false,
                        sort: 0,
                    },
                    { id: 3, groupId: 7, name: "Rent", keywords: "", archived: false, sort: 1 },
                ],
            ],
        ]),
        year,
        currentMonth: 0,
        cols: ["budgeted", "activity", "balance"] as ComponentProps<typeof YearGrid>["cols"],
        collapsed: {},
        setCollapsed: vi.fn(),
        setBudget: vi.fn(),
        onSelectBudget: vi.fn(),
        onCategoryMenu: () => [],
        onAddCategory: vi.fn(),
    };
    const ui = renderUI(<YearGrid {...props} />);
    return { ...ui, props };
}

describe("YearGrid", () => {
    it("shows group totals from all activity but only positive category balances", () => {
        renderGrid();

        const cells = [
            ...screen
                .getByText("Home")
                .closest<HTMLElement>("tr")!
                .querySelectorAll<HTMLElement>("td"),
        ].map((cell) => cell.textContent);
        expect(cells.slice(1, 4)).toEqual(["1 200", "-800", "500"]);
        expect(cells.slice(-2)).toEqual(["-800", "-67"]);
    });

    it("hides category rows on collapse without changing the group subtotal", async () => {
        const { user, props, rerender } = renderGrid();

        await user.click(screen.getByText("Home"));

        expect(props.setCollapsed).toHaveBeenCalledWith({ 7: true });
        rerender(<YearGrid {...props} collapsed={{ 7: true }} />);
        expect(screen.getByText("Home").closest<HTMLElement>("tr")!).toHaveTextContent("-800");
        expect(screen.queryByText("Groceries")).not.toBeInTheDocument();
    });

    it("sends a budget edit to the category and one-based month displayed in the cell", async () => {
        const { user, props } = renderGrid();
        const row = screen.getByText("Rent").closest<HTMLElement>("tr")!;
        const januaryBudget = within(row).getByRole("button", { name: "200" });

        await user.click(januaryBudget);
        const input = screen.getByRole("textbox");
        await user.clear(input);
        await user.type(input, "321");
        await user.keyboard("{Enter}");

        expect(props.setBudget).toHaveBeenCalledWith(3, year, 1, 321_00);
    });

    it("opens the add-category action without also collapsing its group", async () => {
        const { user, props } = renderGrid();

        await user.click(screen.getByLabelText("Add category"));

        expect(props.onAddCategory).toHaveBeenCalledWith(7);
        expect(props.setCollapsed).not.toHaveBeenCalled();
    });

    it("explains January from the previous year and later months from this year", () => {
        const { props, rerender } = renderGrid();
        props.res.available[0] = 1_100_00;
        props.res.available[1] = 2_200_00;
        props.res.overspent[0] = -90_00;
        props.res.income[0] = 700_00;
        props.res.budgetedTotal[0] = 300_00;
        props.res.income[1] = 800_00;
        props.res.budgetedTotal[1] = 400_00;
        const prevRes = {
            year: year - 1,
            available: Array.from({ length: 12 }, (): number => 0),
            overspent: Array.from({ length: 12 }, (): number => 0),
            income: Array.from({ length: 12 }, (): number => 0),
            budgetedTotal: Array.from({ length: 12 }, (): number => 0),
            byCategory: new Map(),
        };
        prevRes.available[11] = 600_00;
        prevRes.overspent[11] = -40_00;

        rerender(<YearGrid {...props} prevRes={prevRes} />);

        expect(screen.getByText("Not budgeted in Dec").previousSibling).toHaveTextContent("600");
        expect(screen.getByText("Overspent in Dec").previousSibling).toHaveTextContent("-40");
        expect(screen.getByText("Not budgeted in Jan").previousSibling).toHaveTextContent("1 100");
        expect(screen.getByText("Income for Feb").previousSibling).toHaveTextContent("800");
        expect(screen.getByText("Budgeted in Feb").previousSibling).toHaveTextContent("-400");
    });

    it("reports the selected category budget with its one-based month", async () => {
        const { user, props } = renderGrid();
        const row = screen.getByText("Groceries").closest<HTMLElement>("tr")!;

        await user.click(within(row).getByRole("button", { name: "1 000" }));

        expect(props.onSelectBudget).toHaveBeenCalledWith({ categoryId: 2, year, month: 1 });
    });
});
