import { describe, expect, it, vi } from "vitest";
import { renderUI, screen, within } from "../test/render.jsx";
import YearGrid from "./YearGrid.jsx";

const year = 2026;
const emptyMonths = () =>
    Array.from({ length: 12 }, () => ({ budgeted: 0, outflows: 0, balance: 0 }));

function renderGrid({ first, second } = {}) {
    const groceries = emptyMonths();
    const rent = emptyMonths();
    Object.assign(
        groceries[0],
        first ?? { budgeted: 1_000_00, outflows: -500_00, balance: 500_00 },
    );
    Object.assign(rent[0], second ?? { budgeted: 200_00, outflows: -300_00, balance: -100_00 });
    const res = {
        available: Array(12).fill(0),
        overspent: Array(12).fill(0),
        income: Array(12).fill(0),
        budgetedTotal: Array(12).fill(0),
        byCategory: new Map([
            [2, groceries],
            [3, rent],
        ]),
    };
    const props = {
        res,
        prevRes: null,
        groups: [{ id: 7, name: "Home" }],
        catsByGroup: new Map([
            [
                7,
                [
                    { id: 2, name: "Groceries" },
                    { id: 3, name: "Rent" },
                ],
            ],
        ]),
        year,
        currentMonth: 0,
        cols: ["budgeted", "activity", "balance"],
        collapsed: {},
        setCollapsed: vi.fn(),
        setBudget: vi.fn(),
        onCategoryMenu: () => [],
        onAddCategory: vi.fn(),
    };
    const ui = renderUI(<YearGrid {...props} />);
    return { ...ui, props };
}

describe("YearGrid", () => {
    it("shows group totals from all activity but only positive category balances", () => {
        renderGrid();

        const cells = [...screen.getByText("Home").closest("tr").querySelectorAll("td")].map(
            (cell) => cell.textContent,
        );
        expect(cells.slice(1, 4)).toEqual(["1 200", "-800", "500"]);
        expect(cells.slice(-2)).toEqual(["-800", "-67"]);
    });

    it("hides category rows on collapse without changing the group subtotal", async () => {
        const { user, props, rerender } = renderGrid();

        await user.click(screen.getByText("Home"));

        expect(props.setCollapsed).toHaveBeenCalledWith({ 7: true });
        rerender(<YearGrid {...props} collapsed={{ 7: true }} />);
        expect(screen.getByText("Home").closest("tr")).toHaveTextContent("-800");
        expect(screen.queryByText("Groceries")).not.toBeInTheDocument();
    });

    it("sends a budget edit to the category and one-based month displayed in the cell", async () => {
        const { user, props } = renderGrid();
        const row = screen.getByText("Rent").closest("tr");
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
});
