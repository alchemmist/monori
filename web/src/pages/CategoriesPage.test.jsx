import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
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
                { id: 2, groupId: 2, name: "Food", keywords: "market|cafe", sort: 1, archived: false },
                { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
            ],
            transactions: [{ id: 1, categoryId: 2 }, { id: 2, categoryId: 2 }, { id: 3, categoryId: 3 }],
        });
        const { container } = renderUI(<CategoriesPage />);

        expect(screen.getByRole("heading", { name: "Categories" })).toBeInTheDocument();
        expect([...container.querySelectorAll(".kb-col__name")].map((el) => el.textContent)).toEqual([
            "Income",
            "Spending",
        ]);
        const spending = container.querySelector('[data-gid="2"]');
        expect([...spending.querySelectorAll(".kb-card__name")].map((el) => el.textContent)).toEqual([
            "Food",
            "Rent",
        ]);
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
        const spending = document.querySelector('[data-gid="2"]');
        await user.click(spending.querySelector(".kb-add-card"));
        expect(screen.getByRole("dialog")).toBeInTheDocument();
        expect(screen.getByLabelText("Name")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "GroupSpending" })).toBeInTheDocument();
    });

    it("archives a category through its row menu", async () => {
        seed({ groups, categories: [{ id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false }] });
        const patchCategory = vi.spyOn(useStore.getState(), "patchCategory").mockResolvedValue();
        const { user } = renderUI(<CategoriesPage />);
        const card = document.querySelector('[data-id="2"]');
        await user.click(card.querySelector("button"));
        await user.click(await screen.findByRole("menuitem", { name: "Archive" }));
        await waitFor(() => expect(patchCategory).toHaveBeenCalledWith(2, { archived: true }));
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
});
