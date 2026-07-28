import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderUI, resetStore, screen, seed, waitFor, within } from "../test/render.jsx";
import { useStore } from "../store.js";
import CategoriesPage from "./CategoriesPage.jsx";

vi.mock("../api.js");

const groups = [
    { id: 2, name: "Spending", kind: "expense", sort: 2 },
    { id: 1, name: "Income", kind: "income", sort: 1 },
];

describe("CategoriesPage", () => {
    beforeEach(() => {
        resetStore();
        vi.clearAllMocks();
    });

    it("orders groups and cards, and displays usage, keywords and archived state", () => {
        seed({
            groups,
            categories: [
                { id: 3, groupId: 2, name: "Rent", keywords: "home", sort: 2, archived: true },
                {
                    id: 2,
                    groupId: 2,
                    name: "Food",
                    keywords: "market|cafe",
                    sort: 1,
                    archived: false,
                },
                { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
            ],
            transactions: [
                { id: 1, categoryId: 2 },
                { id: 2, categoryId: 2 },
                { id: 3, categoryId: 3 },
            ],
        });
        const { container } = renderUI(<CategoriesPage />);

        expect(screen.getByRole("heading", { name: "Categories" })).toBeInTheDocument();
        expect(
            [...container.querySelectorAll(".kb-col__name")].map((el) => el.textContent),
        ).toEqual(["Income", "Spending"]);
        const spending = container.querySelector('[data-gid="2"]');
        expect(
            [...spending.querySelectorAll(".kb-card__name")].map((el) => el.textContent),
        ).toEqual(["Food", "Rent"]);
        expect(spending).toHaveTextContent("market, cafe");
        expect(spending).toHaveTextContent("arch");
        expect(screen.getByTitle("2 transactions")).toBeInTheDocument();
    });

    it("keeps new-category disabled until a group exists", () => {
        seed({ groups: [], categories: [] });
        renderUI(<CategoriesPage />);
        expect(screen.getByRole("button", { name: /new category/i })).toBeDisabled();
    });

    it("opens the category form from a column and preselects its group", async () => {
        seed({ groups, categories: [] });
        const { user } = renderUI(<CategoriesPage />);
        const spending = within(document.querySelector('[data-gid="2"]'));
        await user.click(spending.getByRole("button", { name: /add category/i }));
        expect(screen.getByRole("dialog")).toBeInTheDocument();
        expect(screen.getByLabelText("Name")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "GroupSpending" })).toBeInTheDocument();
    });

    it("starts income and expense group forms from both new-group controls", async () => {
        seed({ groups, categories: [] });
        const { user } = renderUI(<CategoriesPage />);
        await user.click(screen.getByRole("button", { name: "Income" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("New group");

        await user.keyboard("{Escape}");
        await user.click(screen.getByRole("button", { name: "Expense group" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("New group");
    });

    it("opens group and category delete forms from row menus", async () => {
        seed({
            groups,
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
            ],
        });
        const { user, unmount } = renderUI(<CategoriesPage />);
        const group = document.querySelector('[data-gid="2"]');
        await user.click(group.querySelector(".kb-col__head button"));
        await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("Delete Spending");
        unmount();

        renderUI(<CategoriesPage />);
        const card = document.querySelector('[data-id="2"]');
        await user.click(card.querySelector("button"));
        await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("Delete Food");
    });

    it("archives a category through its row menu", async () => {
        seed({
            groups,
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
            ],
        });
        const patchCategory = vi.spyOn(useStore.getState(), "patchCategory").mockResolvedValue();
        const { user } = renderUI(<CategoriesPage />);
        const card = document.querySelector('[data-id="2"]');
        await user.click(card.querySelector("button"));
        await user.click(await screen.findByRole("menuitem", { name: "Archive" }));
        await waitFor(() =>
            expect(patchCategory).toHaveBeenCalledExactlyOnceWith(2, { archived: true }),
        );
    });

    it("offers unarchiving on an archived category and reports a failure", async () => {
        seed({
            groups,
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: true },
            ],
        });
        const patchCategory = vi
            .spyOn(useStore.getState(), "patchCategory")
            .mockRejectedValue(new Error("offline"));
        const { user } = renderUI(<CategoriesPage />);
        const card = document.querySelector('[data-id="2"]');
        await user.click(card.querySelector("button"));
        expect(screen.queryByRole("menuitem", { name: "Archive" })).not.toBeInTheDocument();
        await user.click(await screen.findByRole("menuitem", { name: "Unarchive" }));
        await waitFor(() =>
            expect(patchCategory).toHaveBeenCalledExactlyOnceWith(2, { archived: false }),
        );
        await waitFor(() =>
            expect(useStore.getState().toast).toMatchObject({
                title: "Failed to update category",
                theme: "danger",
            }),
        );
    });

    it("moves a dragged category and persists the resulting board order", () => {
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const card = container.querySelector('[data-id="2"]');
        fireEvent.pointerDown(card, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 20, clientY: 20 });
        fireEvent.pointerUp(window);
        expect(moveCategory).toHaveBeenCalledWith(2, 2, [2, 3]);
    });

    it("moves a category into the hovered group at the computed insertion point", () => {
        vi.stubGlobal("requestAnimationFrame", () => 1);
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        seed({
            groups: [
                { id: 2, name: "Food", kind: "expense", sort: 1 },
                { id: 3, name: "Home", kind: "expense", sort: 2 },
            ],
            categories: [
                { id: 2, groupId: 2, name: "Groceries", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 3, name: "Rent", keywords: "", sort: 1, archived: false },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const source = container.querySelector('[data-id="2"]');
        const sourceGroup = container.querySelector('[data-gid="2"]');
        const destination = container.querySelector('[data-gid="3"]');
        const destinationCards = destination.querySelector(".kb-cards");
        source.getBoundingClientRect = () => ({ left: 0, top: 0, width: 80, height: 30 });
        sourceGroup.getBoundingClientRect = () => ({
            left: 0,
            right: 80,
            top: 0,
            width: 80,
            height: 200,
        });
        destination.getBoundingClientRect = () => ({
            left: 100,
            right: 220,
            top: 0,
            width: 120,
            height: 200,
        });
        destinationCards.querySelector('[data-id="3"]').getBoundingClientRect = () => ({
            top: 50,
            height: 30,
        });

        fireEvent.pointerDown(source, {
            button: 0,
            pointerType: "mouse",
            clientX: 10,
            clientY: 10,
        });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 150, clientY: 100 });
        fireEvent.pointerUp(window);

        expect(moveCategory).toHaveBeenCalledWith(2, 3, [3, 2]);
    });

    it("shows the card's destination slot before dropping it", async () => {
        vi.stubGlobal("requestAnimationFrame", () => 1);
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        seed({
            groups: [
                { id: 2, name: "Food", kind: "expense", sort: 1 },
                { id: 3, name: "Home", kind: "expense", sort: 2 },
            ],
            categories: [
                { id: 2, groupId: 2, name: "Groceries", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 3, name: "Rent", keywords: "", sort: 1, archived: false },
            ],
        });
        const { container } = renderUI(<CategoriesPage />);
        const source = container.querySelector('[data-id="2"]');
        const sourceGroup = container.querySelector('[data-gid="2"]');
        const destination = container.querySelector('[data-gid="3"]');
        source.getBoundingClientRect = () => ({ left: 0, top: 0, width: 80, height: 30 });
        sourceGroup.getBoundingClientRect = () => ({
            left: 0,
            right: 80,
            top: 0,
            width: 80,
            height: 200,
        });
        destination.getBoundingClientRect = () => ({
            left: 100,
            right: 220,
            top: 0,
            width: 120,
            height: 200,
        });
        destination.querySelector('[data-id="3"]').getBoundingClientRect = () => ({
            top: 50,
            height: 30,
        });

        fireEvent.pointerDown(source, {
            button: 0,
            pointerType: "mouse",
            clientX: 10,
            clientY: 10,
        });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 150, clientY: 40 });

        await waitFor(() =>
            expect(
                [
                    ...container.querySelector('[data-gid="3"]').querySelectorAll(".kb-card__name"),
                ].map((card) => card.textContent),
            ).toEqual(["Groceries", "Rent"]),
        );
        expect(container.querySelector('[data-id="2"]')).toHaveClass("kb-card_ghost");
    });

    it("reorders a dragged group and cancels a drag with Escape", () => {
        Object.defineProperty(HTMLElement.prototype, "animate", {
            configurable: true,
            value: () => ({ cancel: () => {} }),
        });
        seed({ groups, categories: [] });
        const reorderGroups = vi.spyOn(useStore.getState(), "reorderGroups").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const income = container.querySelector('[data-gid="1"]');
        const spending = container.querySelector('[data-gid="2"]');
        income.getBoundingClientRect = () => ({
            left: 0,
            right: 100,
            width: 100,
            top: 0,
            height: 100,
        });
        spending.getBoundingClientRect = () => ({
            left: 110,
            right: 210,
            width: 100,
            top: 0,
            height: 100,
        });
        const head = income.querySelector(".kb-col__head");
        fireEvent.pointerDown(head, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 180, clientY: 20 });
        fireEvent.pointerUp(window);
        expect(reorderGroups).toHaveBeenCalledWith([2, 1]);

        fireEvent.pointerDown(head, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 20, clientY: 20 });
        fireEvent.keyDown(window, { key: "Escape" });
        expect(document.body).not.toHaveClass("kb-grabbing");
    });

    it("colours each group tag by its kind and counts its categories", () => {
        seed({
            groups: [
                { id: 1, name: "Income", kind: "income", sort: 1 },
                { id: 2, name: "Spending", kind: "expense", sort: 2 },
                { id: 3, name: "Goals", kind: "goal", sort: 3 },
            ],
            categories: [
                { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
            ],
        });
        const { container } = renderUI(<CategoriesPage />);

        const tagOf = (gid) => container.querySelector(`[data-gid="${gid}"] .kb-col__head .tag`);
        expect(tagOf(1)).toHaveTextContent("income");
        expect(tagOf(1)).toHaveClass("tag_success");
        expect(tagOf(2)).toHaveTextContent("expense");
        expect(tagOf(2)).toHaveClass("tag_danger");
        expect(tagOf(3)).toHaveTextContent("goal");
        expect(tagOf(3)).toHaveClass("tag_info");

        const countOf = (gid) =>
            container.querySelector(`[data-gid="${gid}"] .kb-col__count`).textContent;
        expect(countOf(1)).toBe("1");
        expect(countOf(2)).toBe("2");
        expect(countOf(3)).toBe("0");
    });

    it("labels the add-card button by group kind", () => {
        seed({
            groups: [
                { id: 2, name: "Spending", kind: "expense", sort: 1 },
                { id: 3, name: "Goals", kind: "goal", sort: 2 },
            ],
            categories: [],
        });
        const { container } = renderUI(<CategoriesPage />);
        expect(container.querySelector('[data-gid="2"] .kb-add-card').textContent).toContain(
            "Add category",
        );
        expect(container.querySelector('[data-gid="3"] .kb-add-card').textContent).toContain(
            "Add goal",
        );
    });

    it("renders a goal card with open/closed tag and formatted target", () => {
        seed({
            groups: [{ id: 3, name: "Goals", kind: "goal", sort: 1 }],
            categories: [
                {
                    id: 5,
                    groupId: 3,
                    name: "Car",
                    keywords: "",
                    sort: 1,
                    archived: false,
                    goalTarget: 150000000,
                    goalStatus: "active",
                    goalTargetDate: "2027-01-01",
                },
                {
                    id: 6,
                    groupId: 3,
                    name: "Trip",
                    keywords: "",
                    sort: 2,
                    archived: true,
                    goalTarget: 5000,
                    goalStatus: "archived",
                    goalTargetDate: null,
                },
            ],
        });
        const { container } = renderUI(<CategoriesPage />);

        const car = container.querySelector('[data-id="5"]');
        expect(car.querySelector(".kb-card__top .tag")).toHaveTextContent("open");
        expect(car.querySelector(".kb-card__top .tag")).toHaveClass("tag_success");
        expect(car.querySelector(".kb-card__goal").textContent).toMatch(
            /^Target\s1 500 000\s₽\s·\s2027-01-01$/,
        );

        const trip = container.querySelector('[data-id="6"]');
        expect(trip.querySelector(".kb-card__top .tag")).toHaveTextContent("closed");
        expect(trip.querySelector(".kb-card__top .tag")).toHaveClass("tag_warning");
        expect(trip.querySelector(".kb-card__goal").textContent).toBe("Target 50 ₽");
        expect(trip.querySelector(".kb-card__goal").textContent).not.toContain("·");
    });

    it("shows a New goal button only when a goal group exists and preselects it", async () => {
        seed({
            groups: [
                { id: 2, name: "Spending", kind: "expense", sort: 1 },
                { id: 3, name: "Goals", kind: "goal", sort: 2 },
            ],
            categories: [],
        });
        const { user } = renderUI(<CategoriesPage />);
        await user.click(screen.getByRole("button", { name: /new goal/i }));
        expect(screen.getByRole("dialog")).toHaveTextContent("New category");
        expect(screen.getByRole("button", { name: "GroupGoals" })).toBeInTheDocument();
    });

    it("hides the New goal button without any goal group", () => {
        seed({ groups, categories: [] });
        renderUI(<CategoriesPage />);
        expect(screen.queryByRole("button", { name: /new goal/i })).not.toBeInTheDocument();
    });

    it("preselects the first group when adding a category from the toolbar", async () => {
        seed({ groups, categories: [] });
        const { user } = renderUI(<CategoriesPage />);
        await user.click(screen.getByRole("button", { name: /new category/i }));
        expect(screen.getByRole("button", { name: "GroupIncome" })).toBeInTheDocument();
    });

    it("closes a goal through its row menu via archiveGoal", async () => {
        seed({
            groups: [{ id: 3, name: "Goals", kind: "goal", sort: 1 }],
            categories: [
                {
                    id: 5,
                    groupId: 3,
                    name: "Car",
                    keywords: "",
                    sort: 1,
                    archived: false,
                    goalTarget: 100000,
                    goalStatus: "active",
                },
            ],
        });
        const archiveGoal = vi.spyOn(useStore.getState(), "archiveGoal").mockResolvedValue();
        const { user } = renderUI(<CategoriesPage />);
        const card = document.querySelector('[data-id="5"]');
        await user.click(card.querySelector(".kb-card__menu button"));
        expect(screen.queryByRole("menuitem", { name: "Archive" })).not.toBeInTheDocument();
        await user.click(await screen.findByRole("menuitem", { name: "Close goal" }));
        await waitFor(() => expect(archiveGoal).toHaveBeenCalledExactlyOnceWith(5));
    });

    it("reopens a closed goal through its row menu, restoring active status", async () => {
        seed({
            groups: [{ id: 3, name: "Goals", kind: "goal", sort: 1 }],
            categories: [
                {
                    id: 5,
                    groupId: 3,
                    name: "Car",
                    keywords: "",
                    sort: 1,
                    archived: true,
                    goalTarget: 100000,
                    goalStatus: "archived",
                },
            ],
        });
        const patchCategory = vi.spyOn(useStore.getState(), "patchCategory").mockResolvedValue();
        const { user } = renderUI(<CategoriesPage />);
        const card = document.querySelector('[data-id="5"]');
        await user.click(card.querySelector(".kb-card__menu button"));
        expect(screen.queryByRole("menuitem", { name: "Close goal" })).not.toBeInTheDocument();
        await user.click(await screen.findByRole("menuitem", { name: "Open goal" }));
        await waitFor(() =>
            expect(patchCategory).toHaveBeenCalledExactlyOnceWith(5, {
                archived: false,
                goalStatus: "active",
            }),
        );
    });

    it("opens the category edit form from the Edit row menu item", async () => {
        seed({
            groups,
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
            ],
        });
        const { user } = renderUI(<CategoriesPage />);
        const card = document.querySelector('[data-id="2"]');
        await user.click(card.querySelector(".kb-card__menu button"));
        await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("Edit Food");
    });

    it("opens the group rename form from the group row menu", async () => {
        seed({ groups, categories: [] });
        const { user } = renderUI(<CategoriesPage />);
        const group = document.querySelector('[data-gid="2"]');
        await user.click(group.querySelector(".kb-col__head button"));
        await user.click(await screen.findByRole("menuitem", { name: "Rename & kind" }));
        expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    it("renders comma-joined keywords and drops empty segments", () => {
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                {
                    id: 2,
                    groupId: 2,
                    name: "Food",
                    keywords: "market||cafe|",
                    sort: 1,
                    archived: false,
                },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
            ],
        });
        const { container } = renderUI(<CategoriesPage />);
        expect(container.querySelector('[data-id="2"] .kb-card__kw').textContent).toBe(
            "market, cafe",
        );
        expect(container.querySelector('[data-id="3"] .kb-card__kw')).toBeNull();
    });

    it("shows the transaction usage count and its title on a non-goal card", () => {
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
            ],
            transactions: [
                { id: 1, categoryId: 2 },
                { id: 2, categoryId: 2 },
                { id: 3, categoryId: 2 },
                { id: 4, categoryId: null },
            ],
        });
        const { container } = renderUI(<CategoriesPage />);
        const usage = container.querySelector('[data-id="2"] .kb-card__usage');
        expect(usage.textContent).toBe("3");
        expect(usage).toHaveAttribute("title", "3 transactions");
        expect(container.querySelector('[data-id="2"] .kb-card__top .tag')).toBeNull();
    });

    it("renders income, expense and goal halves in both new-group controls", () => {
        seed({ groups, categories: [] });
        const { container } = renderUI(<CategoriesPage />);
        expect(
            [...container.querySelectorAll(".kb-newgroup__half")].map((b) => b.textContent),
        ).toEqual(["Income", "Expense", "Goals"]);
        expect(
            [...container.querySelectorAll(".kb-col_add__half")].map((b) => b.textContent.trim()),
        ).toEqual(["Income group", "Expense group", "Goals group"]);
    });

    it("starts a goal group from the new-group column goal half", async () => {
        seed({ groups, categories: [] });
        const { user, container } = renderUI(<CategoriesPage />);
        await user.click(container.querySelector(".kb-col_add__half_goal"));
        expect(screen.getByRole("dialog")).toHaveTextContent("New group");
    });

    it("marks only the dragged card as a ghost and shows a clone with its usage count", () => {
        vi.stubGlobal("requestAnimationFrame", () => 1);
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
            ],
            transactions: [
                { id: 1, categoryId: 2 },
                { id: 2, categoryId: 2 },
            ],
        });
        const { container } = renderUI(<CategoriesPage />);
        const card = container.querySelector('[data-id="2"]');
        card.getBoundingClientRect = () => ({ left: 0, top: 0, width: 80, height: 30 });
        container.querySelector('[data-gid="2"]').getBoundingClientRect = () => ({
            left: 0,
            right: 80,
            top: 0,
            width: 80,
            height: 200,
        });
        fireEvent.pointerDown(card, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 40, clientY: 40 });

        expect(container.querySelector('[data-id="2"]')).toHaveClass("kb-card_ghost");
        expect(container.querySelector('[data-id="3"]')).not.toHaveClass("kb-card_ghost");
        const clone = container.querySelector(".kb-card_clone");
        expect(clone).toHaveTextContent("Food");
        expect(clone.querySelector(".kb-card__usage").textContent).toBe("2");
        fireEvent.pointerUp(window);
    });

    it("does not start a drag from a non-primary button", () => {
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const card = container.querySelector('[data-id="2"]');
        fireEvent.pointerDown(card, { button: 1, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 40, clientY: 40 });
        fireEvent.pointerUp(window);
        expect(moveCategory).not.toHaveBeenCalled();
        expect(container.querySelector('[data-id="2"]')).not.toHaveClass("kb-card_ghost");
    });

    it("ignores a tiny pointer movement below the drag threshold", () => {
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const card = container.querySelector('[data-id="2"]');
        fireEvent.pointerDown(card, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 12, clientY: 12 });
        fireEvent.pointerUp(window);
        expect(moveCategory).not.toHaveBeenCalled();
        expect(container.querySelector('[data-id="2"]')).not.toHaveClass("kb-card_ghost");
    });
});
