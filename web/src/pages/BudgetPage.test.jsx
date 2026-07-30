import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderUI, resetStore, screen, seed, waitFor, within } from "../test/render.jsx";
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

/**
 * A snapshot with a goal group (id 3) holding one active goal category (id 4),
 * plus the seed's expense categories. The goal is funded 30 000 of a 100 000
 * target so it stays "active" (visible without Show-unused).
 */
function seedWithGoal(patch = {}) {
    const base = seed();
    return seed({
        groups: [...base.groups, { id: 3, name: "Dreams", kind: "goal", sort: 3 }],
        categories: [
            ...base.categories,
            {
                id: 4,
                groupId: 3,
                name: "Trip",
                keywords: "",
                sort: 1,
                archived: false,
                goalTarget: 100_000_00,
                goalTargetDate: null,
            },
        ],
        budgets: [{ categoryId: 4, year: YEAR, month: 1, amount: 30_000_00 }],
        ...patch,
    });
}

/** A year result that also covers the goal category (id 4). */
function goalResult(goalMonth = () => month(30_000_00, 0)) {
    const base = result();
    base.byCategory.set(
        4,
        Array.from({ length: 12 }, (_, m) => goalMonth(m)),
    );
    return base;
}

function renderGoal(res = goalResult()) {
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

        it("falls back to zeroes for a category the year result does not cover", async () => {
            const { user } = render();
            await user.click(screen.getByRole("button", { name: "Show 1 unused" }));

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

        it("celebrates the exact month an assignment brings to zero, not the current one", async () => {
            const setBudget = vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
            const { user } = render();
            const cells = screen
                .getByText("Groceries")
                .closest("tr")
                .querySelectorAll(".budget-cell");

            // budget January (index 0) up to where its Available hits exactly zero
            await user.click(cells[0]);
            const input = screen.getByRole("textbox");
            await user.clear(input);
            await user.type(input, "30000");
            await user.keyboard("{Enter}");

            const msums = document.querySelectorAll(".yg-msum");
            expect(msums[0]).toHaveClass("yg-msum_complete");
            // only the edited month celebrates — not the current month, not any other
            expect(document.querySelectorAll(".yg-msum_complete")).toHaveLength(1);
            expect(setBudget).toHaveBeenCalledWith(2, YEAR, 1, 30_000_00);
        });

        it("does not celebrate a year-grid month left with money available", async () => {
            vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
            const { user } = render();
            const cells = screen
                .getByText("Groceries")
                .closest("tr")
                .querySelectorAll(".budget-cell");

            // +5 000 leaves 5 000 available in that month — nothing to celebrate
            await user.click(cells[4]);
            const input = screen.getByRole("textbox");
            await user.clear(input);
            await user.type(input, "25000");
            await user.keyboard("{Enter}");

            expect(document.querySelector(".yg-msum_complete")).not.toBeInTheDocument();
        });

        it("celebrates when the remaining amount is only sub-ruble", async () => {
            const setBudget = vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
            const res = result();
            res.available[0] = 10_001;
            const { user } = render(res);
            const cell = screen
                .getByText("Groceries")
                .closest("tr")
                .querySelector(".budget-cell");

            await user.click(cell);
            const input = screen.getByRole("textbox");
            await user.clear(input);
            await user.type(input, "20100");
            await user.keyboard("{Enter}");

            expect(document.querySelector(".yg-msum_complete")).toBeInTheDocument();
            expect(setBudget).toHaveBeenCalledWith(2, YEAR, 1, 2_010_000);
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

        it("defaults to the current year and offers only the years in range", async () => {
            const { user } = renderUI(
                <BudgetPage
                    results={new Map([[YEAR, result()]])}
                    firstYear={YEAR - 2}
                    lastYear={YEAR}
                />,
            );
            const trigger = screen.getByRole("button", { name: String(YEAR) });
            await user.click(trigger);
            const options = [...document.querySelectorAll(".gsel__drop [role='option']")].map(
                (o) => o.textContent,
            );
            expect(options).toEqual([String(YEAR - 2), String(YEAR - 1), String(YEAR)]);
        });

        it("hides the month picker and month-only hero cards in year mode", () => {
            render();
            // "Available to budget" still labels the year grid's corner cap, so the
            // proof that the month hero cards are gone is that no .hero-card renders
            expect(document.querySelector(".hero-card")).toBeNull();
            expect(screen.getByText("Full")).toBeInTheDocument();
        });

        it("orders expense groups ahead of goal groups", () => {
            seedWithGoal();
            renderGoal();
            const names = [...document.querySelectorAll(".yg-group .yg-name")].map((n) =>
                n.textContent.replace(/\d+$/, "").trim(),
            );
            expect(names.indexOf("Living")).toBeLessThan(names.indexOf("Dreams"));
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

        it("celebrates only when a user assignment brings available to exactly zero", async () => {
            const setBudget = vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
            const { user } = render();
            await toMonth(user);

            const hero = screen.getByText("Available to budget").closest(".hero-card");
            expect(hero).not.toHaveClass("hero-card_complete");

            const row = screen.getByText("Groceries").closest("tr");
            await user.click(row.querySelector(".budget-cell"));
            const input = row.querySelector(".budget-cell__input");
            await user.clear(input);
            await user.type(input, "30000");
            await user.keyboard("{Enter}");

            expect(hero).toHaveClass("hero-card_complete");
            // the label never changes and no checkmark appears — the sweep is the whole story
            expect(hero.querySelector(".hero-card__label")).toHaveTextContent(
                "Available to budget",
            );
            expect(setBudget).toHaveBeenCalledWith(2, YEAR, 3, 30_000_00);
        });

        it("celebrates when monthly Available ends with only sub-ruble remainder", async () => {
            const setBudget = vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
            const res = result();
            res.available[2] = 10_001;
            const { user } = render(res);
            await toMonth(user);

            const row = screen.getByText("Groceries").closest("tr");
            await user.click(row.querySelector(".budget-cell"));
            const input = row.querySelector(".budget-cell__input");
            await user.clear(input);
            await user.type(input, "20100");
            await user.keyboard("{Enter}");

            expect(row.closest("body").querySelector(".hero-card_complete")).toBeInTheDocument();
            expect(setBudget).toHaveBeenCalledWith(2, YEAR, 3, 2_010_000);
        });

        it("does not celebrate an already-zero budget on page load", async () => {
            const res = result();
            res.available = Array(12).fill(0);
            const { user } = render(res);
            await toMonth(user);

            expect(screen.getByText("Available to budget").closest(".hero-card")).not.toHaveClass(
                "hero-card_complete",
            );
        });

        it("does not celebrate when a user assignment leaves money available", async () => {
            vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
            const { user } = render(result());
            await toMonth(user);

            const row = screen.getByText("Groceries").closest("tr");
            await user.click(row.querySelector(".budget-cell"));
            const input = row.querySelector(".budget-cell__input");
            await user.clear(input);
            await user.type(input, "25000");
            await user.keyboard("{Enter}");

            expect(screen.getByText("Available to budget").closest(".hero-card")).not.toHaveClass(
                "hero-card_complete",
            );
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

        it("colors the available card as income when positive and shows the month end", async () => {
            const { user } = render();
            await toMonth(user);
            const avail = [...document.querySelectorAll(".hero-card")].find(
                (c) => c.querySelector(".hero-card__label").textContent === "Available to budget",
            );
            const value = avail.querySelector(".hero-card__value");
            expect(value).toHaveStyle({ color: "var(--m-income)" });
            expect(avail).toHaveTextContent("end of March");
        });

        it("colors the available card as expense when negative", async () => {
            const res = result();
            res.available = Array(12).fill(-10_000_00);
            const { user } = render(res);
            await toMonth(user);
            const avail = [...document.querySelectorAll(".hero-card")].find(
                (c) => c.querySelector(".hero-card__label").textContent === "Available to budget",
            );
            expect(avail.querySelector(".hero-card__value")).toHaveStyle({
                color: "var(--m-expense)",
            });
        });

        it("colors overspent red only when below zero, faint otherwise", async () => {
            const negative = render();
            await toMonth(negative.user);
            const overspent = () =>
                [...document.querySelectorAll(".hero-card")]
                    .find((c) => c.querySelector(".hero-card__label").textContent === "Overspent")
                    .querySelector(".hero-card__value");
            expect(overspent()).toHaveStyle({ color: "var(--m-expense)" });

            negative.unmount();
            resetStore();
            seed();
            const res = result();
            res.overspent = Array(12).fill(0);
            const second = render(res);
            await toMonth(second.user);
            expect(overspent()).toHaveStyle({ color: "var(--m-text-faint)" });
        });

        it("skips negative balances when totaling a group's held column", async () => {
            const res = result();
            res.byCategory = new Map([
                [2, Array.from({ length: 12 }, () => month(20_000_00, -25_000_00))],
            ]);
            const { user } = render(res);
            await toMonth(user);
            const group = screen.getByText("Living").closest("tr");
            const cells = [...group.querySelectorAll("td")].map((td) => td.textContent);
            // budgeted 20 000, activity -25 000, balance -5 000 is dropped -> 0
            expect(cells.slice(1, 4)).toEqual([n("20 000"), n("-25 000"), "0"]);
        });

        it("selects the cell's own month when a budget cell is focused", async () => {
            const onSelect = vi.spyOn(useStore.getState(), "setBudget").mockResolvedValue();
            const { user } = render();
            await toMonth(user);
            const row = screen.getByText("Groceries").closest("tr");
            await user.click(row.querySelector(".budget-cell"));
            // the Fill-forward button appears keyed off the selected cell (month 3 < 12)
            expect(
                await screen.findByRole("button", { name: /Fill Groceries to Dec/ }),
            ).toBeInTheDocument();
            onSelect.mockRestore();
        });
    });

    describe("goals", () => {
        const toMonth = async (user, label = "Mar") => {
            await user.click(screen.getByText("Month"));
            await user.click(screen.getByText(label));
        };

        it("keeps an active goal visible and hides funded/inactive ones behind Show unused", () => {
            seedWithGoal();
            renderGoal();
            expect(screen.getByText("Trip")).toBeInTheDocument();
            // the active goal stays visible and is not counted among the unused —
            // only Rent (untouched this year) is, so the toggle reads "Show 1 unused"
            expect(screen.getByRole("button", { name: "Show 1 unused" })).toBeInTheDocument();
        });

        it("counts a fully-funded goal as unused and reveals it on toggle", async () => {
            seedWithGoal({
                budgets: [{ categoryId: 4, year: YEAR, month: 1, amount: 100_000_00 }],
            });
            const { user } = renderGoal();
            expect(screen.queryByText("Trip")).not.toBeInTheDocument();
            // Rent (untouched this year) and the funded Trip goal are both unused
            await user.click(screen.getByRole("button", { name: "Show 2 unused" }));
            expect(screen.getByText("Trip")).toBeInTheDocument();
        });

        it("labels the group as Goals", async () => {
            seedWithGoal();
            const { user } = renderGoal();
            await toMonth(user);
            expect(screen.getByText("Goals")).toBeInTheDocument();
        });

        it("offers Distribute across months when the goal has a target", async () => {
            seedWithGoal();
            const { user } = renderGoal();
            await toMonth(user);
            const row = screen.getByText("Trip").closest("tr");
            await user.click(row.querySelector(".cat-row__menu button"));
            expect(
                await screen.findByRole("menuitem", { name: "Distribute across months" }),
            ).toBeInTheDocument();
            expect(screen.getByRole("menuitem", { name: "Close goal" })).toBeInTheDocument();
        });

        it("asks to set a target first when the goal has none", async () => {
            seedWithGoal();
            useStore.setState((s) => ({
                snapshot: {
                    ...s.snapshot,
                    categories: s.snapshot.categories.map((c) =>
                        c.id === 4 ? { ...c, goalTarget: 0 } : c,
                    ),
                },
            }));
            const { user } = renderGoal();
            await toMonth(user);
            const row = screen.getByText("Trip").closest("tr");
            await user.click(row.querySelector(".cat-row__menu button"));
            expect(
                await screen.findByRole("menuitem", { name: "Set target first" }),
            ).toBeInTheDocument();
        });

        it("archives an open goal through its Close goal menu item", async () => {
            const archiveGoal = vi.spyOn(useStore.getState(), "archiveGoal").mockResolvedValue();
            seedWithGoal();
            const { user } = renderGoal();
            await toMonth(user);
            const row = screen.getByText("Trip").closest("tr");
            await user.click(row.querySelector(".cat-row__menu button"));
            await user.click(await screen.findByRole("menuitem", { name: "Close goal" }));
            await waitFor(() => expect(archiveGoal).toHaveBeenCalledWith(4));
            archiveGoal.mockRestore();
        });

        it("re-opens a closed goal through Open goal", async () => {
            seedWithGoal();
            useStore.setState((s) => ({
                snapshot: {
                    ...s.snapshot,
                    categories: s.snapshot.categories.map((c) =>
                        c.id === 4 ? { ...c, archived: true } : c,
                    ),
                },
            }));
            const patchCategory = vi
                .spyOn(useStore.getState(), "patchCategory")
                .mockResolvedValue();
            const { user } = renderGoal();
            // archived goal is unused; reveal it
            await user.click(screen.getByRole("button", { name: /unused/ }));
            await toMonth(user);
            const row = screen.getByText("Trip").closest("tr");
            await user.click(row.querySelector(".cat-row__menu button"));
            await user.click(await screen.findByRole("menuitem", { name: "Open goal" }));
            await waitFor(() =>
                expect(patchCategory).toHaveBeenCalledWith(4, {
                    archived: false,
                    goalStatus: "active",
                }),
            );
            patchCategory.mockRestore();
        });
    });

    describe("fill forward", () => {
        const toMonth = async (user, label = "Mar") => {
            await user.click(screen.getByText("Month"));
            await user.click(screen.getByText(label));
        };

        it("fills through December with the exact category, year and month", async () => {
            const fill = vi.spyOn(useStore.getState(), "fillBudgetForward").mockResolvedValue(9);
            const { user } = render();
            await toMonth(user);
            await user.click(
                screen.getByText("Groceries").closest("tr").querySelector(".budget-cell"),
            );
            await user.click(await screen.findByRole("button", { name: /Fill Groceries to Dec/ }));
            // March selected -> 1-based month 3
            await waitFor(() => expect(fill).toHaveBeenCalledWith(2, YEAR, 3));
            fill.mockRestore();
        });

        it("pluralizes the filled-months count and singularizes at one", async () => {
            const notify = vi.spyOn(useStore.getState(), "notify");
            const fill = vi.spyOn(useStore.getState(), "fillBudgetForward").mockResolvedValue(1);
            const { user } = render();
            await toMonth(user);
            await user.click(
                screen.getByText("Groceries").closest("tr").querySelector(".budget-cell"),
            );
            await user.click(await screen.findByRole("button", { name: /Fill Groceries to Dec/ }));
            await waitFor(() =>
                expect(notify).toHaveBeenCalledWith(
                    expect.objectContaining({
                        title: "Budget filled through December",
                        content: "Groceries: 1 month",
                        theme: "success",
                    }),
                ),
            );
            fill.mockRestore();
            notify.mockRestore();
        });

        it("adds the plural 's' for a count other than one", async () => {
            const notify = vi.spyOn(useStore.getState(), "notify");
            const fill = vi.spyOn(useStore.getState(), "fillBudgetForward").mockResolvedValue(9);
            const { user } = render();
            await toMonth(user);
            await user.click(
                screen.getByText("Groceries").closest("tr").querySelector(".budget-cell"),
            );
            await user.click(await screen.findByRole("button", { name: /Fill Groceries to Dec/ }));
            await waitFor(() =>
                expect(notify).toHaveBeenCalledWith(
                    expect.objectContaining({
                        title: "Budget filled through December",
                        content: "Groceries: 9 months",
                        theme: "success",
                    }),
                ),
            );
            fill.mockRestore();
            notify.mockRestore();
        });

        it("does not offer fill forward for a December cell", async () => {
            const { user } = render();
            await toMonth(user, "Dec");
            await user.click(
                screen.getByText("Groceries").closest("tr").querySelector(".budget-cell"),
            );
            expect(
                screen.queryByRole("button", { name: /Fill Groceries to Dec/ }),
            ).not.toBeInTheDocument();
        });
    });

    describe("GoalUrgency", () => {
        // the badge counts down from the real clock, so pin "today" or the exact
        // "19d left" / overdue / quiet branches would drift as the date advances
        beforeEach(() => {
            vi.useFakeTimers({ shouldAdvanceTime: true });
            vi.setSystemTime(new Date("2026-07-28T12:00:00"));
        });
        afterEach(() => vi.useRealTimers());

        const withDate = (date) =>
            seedWithGoal({
                categories: [
                    ...seed().categories,
                    {
                        id: 4,
                        groupId: 3,
                        name: "Trip",
                        keywords: "",
                        sort: 1,
                        archived: false,
                        goalTarget: 100_000_00,
                        goalTargetDate: date,
                    },
                ],
                groups: [...seed().groups, { id: 3, name: "Dreams", kind: "goal", sort: 3 }],
            });

        const openTooltip = async (user) => {
            // urgency only rides along with the goal label in month mode
            await user.click(screen.getByText("Month"));
            await user.click(screen.getByText("Mar"));
            await user.hover(screen.getByText("Trip"));
            const funded = await waitFor(() => screen.getByText(/30 000 \/ 100 000/));
            // the urgency badge is a sibling span; assert on the whole popup
            return funded.closest(".goal-label__popup");
        };

        it("shows a countdown when the deadline is within 60 days and underfunded", async () => {
            withDate("2026-08-15");
            const { user } = renderGoal();
            const tip = await openTooltip(user);
            expect(tip.textContent).toMatch(/🔥 19d left/);
        });

        it("marks an overdue underfunded goal", async () => {
            withDate("2026-07-01");
            const { user } = renderGoal();
            const tip = await openTooltip(user);
            expect(tip.textContent).toMatch(/overdue/);
        });

        it("stays quiet when the deadline is more than 60 days out", async () => {
            withDate("2026-12-31");
            const { user } = renderGoal();
            const tip = await openTooltip(user);
            expect(tip.textContent).not.toMatch(/left|overdue/);
        });

        it("still shows the countdown at exactly 60 days but not at 61", async () => {
            // 2026-09-25 is 60 days out (shows), 2026-09-26 is 61 (quiet):
            // pins the `days > 60` threshold on both sides
            withDate("2026-09-25");
            const shown = renderGoal();
            let tip = await openTooltip(shown.user);
            expect(tip.textContent).toMatch(/🔥 60d left/);
            shown.unmount();

            resetStore();
            withDate("2026-09-26");
            const { user } = renderGoal();
            tip = await openTooltip(user);
            expect(tip.textContent).not.toMatch(/left|overdue/);
        });

        it("counts today as a live countdown, not overdue", async () => {
            // 2026-07-27T23:59:59 is 0 days out (Math.ceil gives -0, which is not
            // < 0): the badge reads "0d left", proving the `days < 0` cutoff is
            // strict and does not fire at zero
            withDate("2026-07-27");
            const { user } = renderGoal();
            const tip = await openTooltip(user);
            expect(tip.textContent).toMatch(/🔥 0d left/);
            expect(tip.textContent).not.toMatch(/overdue/);
        });
    });

    describe("DistributeGoalDialog", () => {
        const toMonth = async (user, label = "Mar") => {
            await user.click(screen.getByText("Month"));
            await user.click(screen.getByText(label));
        };

        const openDistribute = async (user) => {
            await toMonth(user);
            const row = screen.getByText("Trip").closest("tr");
            await user.click(row.querySelector(".cat-row__menu button"));
            await user.click(
                await screen.findByRole("menuitem", { name: "Distribute across months" }),
            );
            return screen.getByRole("dialog");
        };

        it("suggests the month count implied by the target date", async () => {
            seedWithGoal({
                groups: [...seed().groups, { id: 3, name: "Dreams", kind: "goal", sort: 3 }],
                categories: [
                    ...seed().categories,
                    {
                        id: 4,
                        groupId: 3,
                        name: "Trip",
                        keywords: "",
                        sort: 1,
                        archived: false,
                        goalTarget: 100_000_00,
                        goalTargetDate: "2026-06-01",
                    },
                ],
                budgets: [{ categoryId: 4, year: YEAR, month: 1, amount: 30_000_00 }],
            });
            const { user } = renderGoal();
            const dialog = await openDistribute(user);
            // start March (3), target June (6): 6-3+1 = 4 months
            expect(within(dialog).getByRole("spinbutton")).toHaveValue(4);
        });

        it("splits the remaining target across months, front-loading the remainder", async () => {
            const setBudgets = vi.spyOn(useStore.getState(), "setBudgets").mockResolvedValue();
            seedWithGoal();
            const { user } = renderGoal();
            const dialog = await openDistribute(user);
            const input = within(dialog).getByRole("spinbutton");
            fireEvent.change(input, { target: { value: "3" } });
            await user.click(within(dialog).getByRole("button", { name: "Distribute" }));

            // target 100 000, already 30 000 before March -> 70 000 over 3 months,
            // base 2 333 333 kop, remainder 1 kop to the first cell
            await waitFor(() => expect(setBudgets).toHaveBeenCalled());
            const cells = setBudgets.mock.calls[0][0];
            expect(cells.slice(0, 3)).toEqual([
                { categoryId: 4, year: YEAR, month: 3, amount: 2_333_334 },
                { categoryId: 4, year: YEAR, month: 4, amount: 2_333_333 },
                { categoryId: 4, year: YEAR, month: 5, amount: 2_333_333 },
            ]);
            setBudgets.mockRestore();
        });

        it("disables Distribute for a non-positive month count", async () => {
            seedWithGoal();
            const { user } = renderGoal();
            const dialog = await openDistribute(user);
            const input = within(dialog).getByRole("spinbutton");
            fireEvent.change(input, { target: { value: "0" } });
            expect(within(dialog).getByRole("button", { name: "Distribute" })).toBeDisabled();
        });

        it("rejects more than 120 months", async () => {
            seedWithGoal();
            const { user } = renderGoal();
            const dialog = await openDistribute(user);
            const input = within(dialog).getByRole("spinbutton");
            fireEvent.change(input, { target: { value: "121" } });
            expect(within(dialog).getByRole("button", { name: "Distribute" })).toBeDisabled();
        });

        it("counts whole years toward the suggested month span", async () => {
            // start March 2026 (month 3), target February 2028: two full years plus
            // (2 - 3) months plus 1 = 24 - 1 + 1 = 24 months. This exercises the
            // year term (* 12) and both -startYear / -startMonth subtractions.
            seedWithGoal({
                groups: [...seed().groups, { id: 3, name: "Dreams", kind: "goal", sort: 3 }],
                categories: [
                    ...seed().categories,
                    {
                        id: 4,
                        groupId: 3,
                        name: "Trip",
                        keywords: "",
                        sort: 1,
                        archived: false,
                        goalTarget: 100_000_00,
                        goalTargetDate: "2028-02-01",
                    },
                ],
                budgets: [{ categoryId: 4, year: YEAR, month: 1, amount: 30_000_00 }],
            });
            const { user } = renderGoal();
            const dialog = await openDistribute(user);
            // (2028 - 2026) * 12 + (2 - 3) + 1 = 24
            expect(within(dialog).getByRole("spinbutton")).toHaveValue(24);
        });

        it("rolls the plan into the next year and appends zeroes for orphaned future budgets", async () => {
            const setBudgets = vi.spyOn(useStore.getState(), "setBudgets").mockResolvedValue();
            seedWithGoal({
                // 30 000 already parked before March lowers the remaining target to
                // 70 000; a June-2027 budget past the planned window must be zeroed
                // out so the goal isn't overfunded
                budgets: [
                    { categoryId: 4, year: YEAR, month: 1, amount: 30_000_00 },
                    { categoryId: 4, year: YEAR + 1, month: 6, amount: 5_000_00 },
                ],
            });
            const { user } = renderGoal();
            const dialog = await openDistribute(user);
            const input = within(dialog).getByRole("spinbutton");
            // 12 months from March 2026 crosses into 2027 (Jan, Feb)
            fireEvent.change(input, { target: { value: "12" } });
            await user.click(within(dialog).getByRole("button", { name: "Distribute" }));

            await waitFor(() => expect(setBudgets).toHaveBeenCalled());
            const cells = setBudgets.mock.calls[0][0];
            // 70 000 00 kop over 12 months: base 583 333 kop, 4 kop remainder
            // front-loaded onto the first four cells
            expect(cells.slice(0, 12)).toEqual([
                { categoryId: 4, year: YEAR, month: 3, amount: 583_334 },
                { categoryId: 4, year: YEAR, month: 4, amount: 583_334 },
                { categoryId: 4, year: YEAR, month: 5, amount: 583_334 },
                { categoryId: 4, year: YEAR, month: 6, amount: 583_334 },
                { categoryId: 4, year: YEAR, month: 7, amount: 583_333 },
                { categoryId: 4, year: YEAR, month: 8, amount: 583_333 },
                { categoryId: 4, year: YEAR, month: 9, amount: 583_333 },
                { categoryId: 4, year: YEAR, month: 10, amount: 583_333 },
                { categoryId: 4, year: YEAR, month: 11, amount: 583_333 },
                { categoryId: 4, year: YEAR, month: 12, amount: 583_333 },
                { categoryId: 4, year: YEAR + 1, month: 1, amount: 583_333 },
                { categoryId: 4, year: YEAR + 1, month: 2, amount: 583_333 },
            ]);
            // the pre-March January budget is left untouched (not in the cells),
            // and the orphaned June-2027 budget is re-emitted at zero
            expect(cells).toContainEqual({
                categoryId: 4,
                year: YEAR + 1,
                month: 6,
                amount: 0,
            });
            expect(cells.some((c) => c.year === YEAR && c.month === 1)).toBe(false);
            setBudgets.mockRestore();
        });
    });
});
