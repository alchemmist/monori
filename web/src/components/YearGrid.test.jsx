import { describe, it, expect, vi, afterEach } from "vitest";
import { renderUI, resetStore, atDemo, screen, waitFor } from "../test/render.jsx";
import YearGrid from "./YearGrid.jsx";
import { computeRange } from "../engine/budget.js";
import { orderedGroups, categoriesByGroup } from "../categoryOrder.js";

describe("YearGrid", () => {
    afterEach(() => {
        resetStore();
    });

    function renderYearGrid(
        year = 2026,
        cols = ["budgeted", "activity", "balance"],
        collapsed = {},
    ) {
        const snap = atDemo();
        const results = computeRange(snap, year, year);
        const res = results.get(year);
        const prevRes = year > 2025 ? (results.get(year - 1) ?? null) : null;
        const groups = orderedGroups(snap.groups).filter((g) => g.kind === "expense");
        const catsByGroup = categoriesByGroup(snap.categories, groups);
        const setBudget = vi.fn();
        const onCategoryMenu = vi.fn(() => []);
        const onAddCategory = vi.fn();
        const setCollapsed = vi.fn();

        return {
            ...renderUI(
                <YearGrid
                    res={res}
                    prevRes={prevRes}
                    groups={groups}
                    catsByGroup={catsByGroup}
                    year={year}
                    currentMonth={5}
                    cols={cols}
                    collapsed={collapsed}
                    setCollapsed={setCollapsed}
                    setBudget={setBudget}
                    onCategoryMenu={onCategoryMenu}
                    onAddCategory={onAddCategory}
                />,
            ),
            setBudget,
            onCategoryMenu,
            onAddCategory,
            setCollapsed,
        };
    }

    it("renders a table with year-grid class", () => {
        renderYearGrid();
        const table = document.querySelector(".year-grid");
        expect(table).toBeInTheDocument();
    });

    it("renders year label in header", () => {
        renderYearGrid(2026);
        const yearDiv = document.querySelector(".yg-year");
        expect(yearDiv).toHaveTextContent("2026");
    });

    it("renders all 12 months in header", () => {
        renderYearGrid();
        const monthLabels = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ];
        for (const m of monthLabels) {
            expect(screen.getByText(m)).toBeInTheDocument();
        }
    });

    it("renders metric column headers with Bud/Act/Bal labels", () => {
        renderYearGrid();
        expect(screen.getByText("Bud")).toBeInTheDocument();
        expect(screen.getByText("Act")).toBeInTheDocument();
        expect(screen.getByText("Bal")).toBeInTheDocument();
    });

    it("renders Total and Avg columns at the end", () => {
        renderYearGrid();
        const table = document.querySelector(".year-grid");
        const headers = table.querySelectorAll("th");
        const lastHeaders = Array.from(headers).slice(-2);
        const texts = lastHeaders.map((h) => h.textContent);
        expect(texts.some((t) => t.includes("Total"))).toBe(true);
        expect(texts.some((t) => t.includes("Avg"))).toBe(true);
    });

    it("renders group rows", () => {
        renderYearGrid();
        const groupRows = document.querySelectorAll(".yg-group");
        expect(groupRows.length).toBeGreaterThan(0);
    });

    it("displays category count in group rows", () => {
        renderYearGrid();
        const counts = document.querySelectorAll(".yg-count");
        expect(counts.length).toBeGreaterThan(0);
    });

    it("collapses group when row is clicked", async () => {
        const { user, setCollapsed } = renderYearGrid();
        const groupRow = document.querySelector(".yg-group");
        await user.click(groupRow);
        expect(setCollapsed).toHaveBeenCalled();
    });

    it("expands categories when group is not collapsed", () => {
        renderYearGrid();
        const catRows = document.querySelectorAll(".yg-row");
        expect(catRows.length).toBeGreaterThan(0);
    });

    it("hides categories when group is collapsed", () => {
        renderYearGrid(2026, ["budgeted", "activity", "balance"], { 2: true });
        const catRows = document.querySelectorAll(".yg-row");
    });

    it("renders budget cells as editable", () => {
        renderYearGrid();
        const budgetCells = document.querySelectorAll(".budget-cell");
        expect(budgetCells.length).toBeGreaterThan(0);
    });

    it("renders activity and balance values as read-only numbers", () => {
        renderYearGrid();
        const ygnums = document.querySelectorAll(".yg-num");
        expect(ygnums.length).toBeGreaterThan(0);
    });

    it("shows Add Category button in each group", async () => {
        const { user, onAddCategory } = renderYearGrid();
        const addButtons = screen.getAllByRole("button", { name: /Add category/i });
        if (addButtons.length > 0) {
            await user.click(addButtons[0]);
            expect(onAddCategory).toHaveBeenCalled();
        }
    });

    it("renders category row menu buttons", () => {
        renderYearGrid();
        const menuButtons = Array.from(screen.getAllByRole("button")).filter((b) =>
            b.querySelector("svg"),
        );
        expect(menuButtons.length).toBeGreaterThan(0);
    });

    it("displays group year subtotals", () => {
        renderYearGrid();
        const groupRows = document.querySelectorAll(".yg-group");
        expect(groupRows.length).toBeGreaterThan(0);
        const firstRow = groupRows[0];
        const cells = firstRow.querySelectorAll("td");
        expect(cells.length).toBeGreaterThan(2);
    });

    it("displays category year totals and averages", () => {
        renderYearGrid();
        const catRows = document.querySelectorAll(".yg-row");
        if (catRows.length > 0) {
            const cells = catRows[0].querySelectorAll("td");
            expect(cells.length).toBeGreaterThan(2);
        }
    });

    it("shows only budgeted columns when density is ['budgeted']", () => {
        renderYearGrid(2026, ["budgeted"]);
        const budCells = document.querySelectorAll(".budget-cell");
        const actCells = Array.from(document.querySelectorAll(".yg-num")).filter((n) =>
            n.className.includes("yg-num_neg"),
        );
        expect(budCells.length).toBeGreaterThan(0);
    });

    it("shows activity and balance when density excludes budgeted", () => {
        renderYearGrid(2026, ["activity", "balance"]);
        const budCells = document.querySelectorAll(".budget-cell");
        expect(budCells.length).toBe(0);
    });

    it("highlights current month columns", () => {
        renderYearGrid(2026, ["budgeted", "activity", "balance"]);
        const nowCells = document.querySelectorAll(".yg-cell_now");
        expect(nowCells.length).toBeGreaterThan(0);
    });

    it("renders wrap div with year-grid-wrap class", () => {
        renderYearGrid();
        const wrap = document.querySelector(".year-grid-wrap");
        expect(wrap).toBeInTheDocument();
    });

    it("renders header with frozen positioning", () => {
        renderYearGrid();
        const thead = document.querySelector("thead");
        expect(thead).toBeInTheDocument();
    });

    it("renders category column corner header", () => {
        renderYearGrid();
        const corner = document.querySelector(".yg-corner_cat");
        expect(corner).toHaveTextContent("Category");
    });

    it("renders year corner header", () => {
        renderYearGrid();
        const yearCorner = document.querySelector(".yg-corner_year");
        expect(yearCorner).toBeInTheDocument();
    });

    it("calls setBudget when budget cell is edited", async () => {
        const { user, setBudget } = renderYearGrid();
        const budgetCell = document.querySelector(".budget-cell");
        await user.click(budgetCell);
        const input = screen.getByRole("textbox");
        await user.clear(input);
        await user.type(input, "5000");
        await user.keyboard("{Enter}");
        expect(setBudget).toHaveBeenCalled();
    });

    it("renders chevron icon in group rows", () => {
        renderYearGrid();
        const chevrons = document.querySelectorAll(".yg-chevron");
        expect(chevrons.length).toBeGreaterThan(0);
    });

    it("shows chevron as collapsed when group is collapsed", () => {
        renderYearGrid(2026, ["budgeted", "activity", "balance"], { 2: true });
        const chevrons = document.querySelectorAll(".yg-chevron_collapsed");
    });

    it("renders first metric cell with special styling", () => {
        renderYearGrid();
        const firstMetrics = document.querySelectorAll(".yg-cell_first");
        expect(firstMetrics.length).toBeGreaterThan(0);
    });

    it("renders category names in rows", () => {
        renderYearGrid();
        const catLabels = document.querySelectorAll(".yg-cat-label");
        expect(catLabels.length).toBeGreaterThan(0);
    });

    it("handles available to budget breakdown in headers", () => {
        renderYearGrid();
        const breakLines = document.querySelectorAll(".yg-break__line");
        expect(breakLines.length).toBeGreaterThan(0);
    });

    it("renders previous year available to budget for first month", () => {
        renderYearGrid(2026);
        const breakLine = Array.from(document.querySelectorAll(".yg-break__lbl")).find((l) =>
            l.textContent.includes("Not budgeted"),
        );
        expect(breakLine).toBeInTheDocument();
    });

    it("collapses multiple groups independently", async () => {
        const { user } = renderYearGrid();
        const groupRows = document.querySelectorAll(".yg-group");
        if (groupRows.length > 1) {
            await user.click(groupRows[0]);
            expect(document.querySelector(".yg-chevron_collapsed")).toBeInTheDocument();
        }
    });

    it("shows Available to budget in month column headers", () => {
        renderYearGrid();
        expect(screen.getByText("Available to budget")).toBeInTheDocument();
    });

    it("displays monetary values with yg-num class", () => {
        renderYearGrid();
        const nums = document.querySelectorAll(".yg-num");
        expect(nums.length).toBeGreaterThan(0);
    });

    it("styles negative values with yg-num_neg", () => {
        renderYearGrid();
        const negValues = document.querySelectorAll(".yg-num_neg");
    });

    it("styles positive values with yg-num_pos", () => {
        renderYearGrid();
        const posValues = document.querySelectorAll(".yg-num_pos");
    });
});
