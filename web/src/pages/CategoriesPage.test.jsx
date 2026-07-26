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
        sourceGroup.getBoundingClientRect = () => ({ left: 0, right: 80, top: 0, width: 80, height: 200 });
        destination.getBoundingClientRect = () => ({ left: 100, right: 220, top: 0, width: 120, height: 200 });
        destinationCards.querySelector('[data-id="3"]').getBoundingClientRect = () => ({
            top: 50,
            height: 30,
        });

        fireEvent.pointerDown(source, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
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
        destination.getBoundingClientRect = () => ({ left: 100, right: 220, top: 0, width: 120, height: 200 });
        destination.querySelector('[data-id="3"]').getBoundingClientRect = () => ({
            top: 50,
            height: 30,
        });

        fireEvent.pointerDown(source, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 150, clientY: 40 });

        await waitFor(() =>
            expect(
                [...container.querySelector('[data-gid="3"]').querySelectorAll(".kb-card__name")].map(
                    (card) => card.textContent,
                ),
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
});
