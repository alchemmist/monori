import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import BudgetPage from "./BudgetPage.jsx";

const YEAR = 2026;

/** A month of one category: what the engine would hand the page. */
const month = (budgeted, outflows) => ({ budgeted, outflows, balance: budgeted + outflows });

/**
 * A year result shaped like the engine's, with the same numbers in every month
 * unless a test overrides them. Groceries (id 2) is the only budgeted category;
 * Rent (id 3) is deliberately left out so the page's "no data" fallback shows.
 */
function result({ groceries = () => month(20_000_00, -5_000_00) } = {}) {
    return {
        available: Array(12).fill(10_000_00),
        overspent: Array(12).fill(-500_00),
        income: Array(12).fill(50_000_00),
        budgetedTotal: Array(12).fill(20_000_00),
        byCategory: new Map([[2, Array.from({ length: 12 }, (_, m) => groceries(m))]]),
    };
}

const results = (res = result()) => new Map([[YEAR, res]]);

function render(res) {
    return renderUI(<BudgetPage results={results(res)} firstYear={YEAR} lastYear={YEAR} />);
}

// ru-RU groups thousands with a non-breaking space; expected strings are written
// with plain spaces and only the digit groups swapped.
const n = (s) => s.replace(/(\d) (?=\d)/g, "$1 ");

describe("BudgetPage", () => {
    beforeEach(() => {
        resetStore();
        seed();
    });

    describe("year mode", () => {
        it("renders every expense category with its yearly totals", () => {
            render();

            expect(screen.getByRole("heading", { name: "Budget" })).toBeInTheDocument();
            const row = screen.getByText("Groceries").closest("tr");
            const totals = [...row.querySelectorAll(".yg-total")].map((td) => td.textContent);
            // 12 × -5 000 spent, and its monthly average
            expect(totals).toEqual([n("-60 000"), n("-5 000")]);
        });

        it("falls back to zeroes for a category the year result does not cover", () => {
            render();

            const row = screen.getByText("Rent").closest("tr");
            expect([...row.querySelectorAll(".yg-total")].map((td) => td.textContent)).toEqual([
                "0",
                "0",
            ]);
        });

        it("heads each month with its available-to-budget breakdown", () => {
            render();

            const jan = screen.getByText(`Jan ${YEAR}`).closest("th");
            expect(jan.querySelector(".yg-msum__av")).toHaveTextContent("10 000 ₽");
            const breakdown = [...jan.querySelectorAll(".yg-break__line")].map(
                (l) => l.textContent,
            );
            expect(breakdown).toEqual([
                n("0Not budgeted in Dec"),
                n("0Overspent in Dec"),
                n("50 000Income for Jan"),
                n("-20 000Budgeted in Jan"),
            ]);
        });

        it("shows only the budgeted column in Plan density", async () => {
            const { user } = render();

            expect(document.querySelectorAll(".yg-metric")).toHaveLength(36);

            await user.click(screen.getByText("Plan"));

            const labels = [...document.querySelectorAll(".yg-metric")].map((th) => th.textContent);
            expect(labels).toHaveLength(12);
            expect(new Set(labels)).toEqual(new Set(["Bud"]));
        });

        it("saves a year-grid budget edit against the month it sits in", async () => {
            const setBudget = vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
            const { user } = render();

            // one budget cell per month, in calendar order — March is the third
            const cells = screen
                .getByText("Groceries")
                .closest("tr")
                .querySelectorAll(".budget-cell");
            expect(cells).toHaveLength(12);
            await user.click(cells[2]);
            const input = document.querySelector(".budget-cell__input");
            await user.clear(input);
            await user.type(input, "300");
            await user.keyboard("{Enter}");

            await waitFor(() => expect(setBudget).toHaveBeenCalledWith(2, YEAR, 3, 300_00));
        });
    });

    describe("month mode", () => {
        const toMonth = async (user, label = "Mar") => {
            await user.click(screen.getByText("Month"));
            await user.click(screen.getByText(label));
        };

        it("shows the month's hero metrics", async () => {
            const { user } = render();
            await toMonth(user);

            const hero = (label) =>
                [...document.querySelectorAll(".hero-card")].find(
                    (c) => c.querySelector(".hero-card__label").textContent === label,
                );
            expect(hero("Available to budget")).toHaveTextContent("10 000 ₽");
            expect(hero("Income")).toHaveTextContent("50 000 ₽");
            expect(hero("Income")).toHaveTextContent(`March ${YEAR}`);
            expect(hero("Budgeted")).toHaveTextContent("20 000 ₽");
            expect(hero("Overspent")).toHaveTextContent("-500 ₽");
        });

        it("totals a group row from the categories under it", async () => {
            const { user } = render();
            await toMonth(user);

            const group = screen.getByText("Living").closest("tr");
            const cells = [...group.querySelectorAll("td")].map((td) => td.textContent);
            // category column, budgeted, activity, balance
            expect(cells.slice(1, 4)).toEqual([n("20 000"), n("-5 000"), n("15 000")]);
        });

        it("collapses a group away and back", async () => {
            const { user } = render();
            await toMonth(user);

            await user.click(screen.getByText("Living"));
            expect(screen.queryByText("Groceries")).not.toBeInTheDocument();

            await user.click(screen.getByText("Living"));
            expect(screen.getByText("Groceries")).toBeInTheDocument();
        });

        it("saves a monthly budget edit against the selected month", async () => {
            const setBudget = vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
            const { user } = render();
            await toMonth(user);

            const row = screen.getByText("Groceries").closest("tr");
            await user.click(row.querySelector(".budget-cell"));
            const input = row.querySelector(".budget-cell__input");
            await user.clear(input);
            await user.type(input, "300");
            await user.keyboard("{Enter}");

            // March is month index 2, and setBudget takes 1-based months
            await waitFor(() => expect(setBudget).toHaveBeenCalledWith(2, YEAR, 3, 300_00));
        });

        it("caps the spent bar at the full width once the envelope is emptied", async () => {
            const { user } = render(result({ groceries: () => month(10_000_00, -30_000_00) }));
            await toMonth(user);

            const fill = screen
                .getByText("Groceries")
                .closest("tr")
                .querySelector(".cat-progress__fill");
            // 30 000 spent of a 10 000 budget is 300%, but the bar stops at 100%
            expect(fill).toHaveStyle({ width: "100%" });
            expect(fill).toHaveStyle({ background: "var(--m-expense)" });
        });

        it("fills the spent bar proportionally while the envelope holds", async () => {
            const { user } = render(result({ groceries: () => month(10_000_00, -2_500_00) }));
            await toMonth(user);

            const fill = screen
                .getByText("Groceries")
                .closest("tr")
                .querySelector(".cat-progress__fill");
            expect(fill).toHaveStyle({ width: "25%" });
            expect(fill).toHaveStyle({ background: "var(--m-accent)" });
        });

        it("opens the new-category form from the group's plus button", async () => {
            const { user } = render();
            await toMonth(user);

            await user.click(screen.getByLabelText("Add category"));
            expect(screen.getByText("New category")).toBeInTheDocument();
        });

        it("opens the delete form for a category from its row menu", async () => {
            const { user } = render();
            await toMonth(user);

            const row = screen.getByText("Groceries").closest("tr");
            await user.click(row.querySelector(".cat-row__menu button"));
            await user.click(await screen.findByRole("menuitem", { name: "Delete" }));

            expect(screen.getByRole("dialog")).toHaveTextContent("Delete Groceries");
        });
    });
});
