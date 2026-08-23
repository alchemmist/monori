import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderUI, resetStore, screen, seed, waitFor, within } from "../test/render.jsx";
import { useStore } from "../store.js";
import CategoriesPage from "./CategoriesPage.jsx";

vi.mock("../api.js");

const groups = [
    { id: 2, name: "Spending", kind: "expense", sort: 2 },
    { id: 1, name: "Income", kind: "income", sort: 1 },
];

function dragCardToGroup(container: HTMLElement, cardId: number, groupId: number) {
    vi.stubGlobal("requestAnimationFrame", () => 1);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const card = container.querySelector<HTMLElement>(`[data-id="${cardId}"]`)!;
    const sourceGroup = card.closest<HTMLElement>("[data-gid]")!;
    const destination = container.querySelector<HTMLElement>(`[data-gid="${groupId}"]`)!;
    card.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
    sourceGroup.getBoundingClientRect = () =>
        DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 200 });
    destination.getBoundingClientRect = () =>
        DOMRect.fromRect({ x: 100, y: 0, width: 120, height: 200 });
    for (const destinationCard of destination.querySelectorAll<HTMLElement>("[data-id]")) {
        destinationCard.getBoundingClientRect = () =>
            DOMRect.fromRect({ x: 100, y: 50, width: 80, height: 30 });
    }
    fireEvent.pointerDown(card, {
        button: 0,
        pointerType: "mouse",
        clientX: 10,
        clientY: 10,
    });
    fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 150, clientY: 100 });
    fireEvent.pointerUp(window);
}

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
            [...container.querySelectorAll<HTMLElement>(".kb-col__name")].map(
                (el) => el.textContent,
            ),
        ).toEqual(["Income", "Spending"]);
        const spending = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        expect(
            [...spending.querySelectorAll<HTMLElement>(".kb-card__name")].map(
                (el) => el.textContent,
            ),
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
        const spending = within(document.querySelector<HTMLElement>('[data-gid="2"]')!);
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
        const group = document.querySelector<HTMLElement>('[data-gid="2"]')!;
        await user.click(group.querySelector<HTMLElement>(".kb-col__head button")!);
        await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("Delete Spending");
        unmount();

        renderUI(<CategoriesPage />);
        const card = document.querySelector<HTMLElement>('[data-id="2"]')!;
        await user.click(card.querySelector<HTMLElement>("button")!);
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
        const card = document.querySelector<HTMLElement>('[data-id="2"]')!;
        await user.click(card.querySelector<HTMLElement>("button")!);
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
        const card = document.querySelector<HTMLElement>('[data-id="2"]')!;
        await user.click(card.querySelector<HTMLElement>("button")!);
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
        const card = container.querySelector<HTMLElement>('[data-id="2"]')!;
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
        const source = container.querySelector<HTMLElement>('[data-id="2"]')!;
        const sourceGroup = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        const destination = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        const destinationCards = destination.querySelector<HTMLElement>(".kb-cards")!;
        source.getBoundingClientRect = () =>
            DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
        sourceGroup.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        destination.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 100,
                y: 0,
                width: 120,
                height: 200,
            });
        destinationCards.querySelector<HTMLElement>('[data-id="3"]')!.getBoundingClientRect = () =>
            DOMRect.fromRect({
                y: 50,
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

    it("asks for a target before moving a category into a goals group", async () => {
        seed({
            groups: [
                { id: 2, name: "Spending", kind: "expense", sort: 1 },
                { id: 3, name: "Plans", kind: "goal", sort: 2 },
            ],
            categories: [
                { id: 2, groupId: 2, name: "Vacation", keywords: "", sort: 1, archived: false },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container, user } = renderUI(<CategoriesPage />);

        dragCardToGroup(container, 2, 3);

        expect(moveCategory).not.toHaveBeenCalled();
        expect(screen.getByText("Set a goal for Vacation")).toBeInTheDocument();
        await user.type(screen.getByLabelText("Target, ₽"), "7500");
        fireEvent.change(screen.getByLabelText("Deadline (optional)"), {
            target: { value: "2027-06-01" },
        });
        await user.click(screen.getByRole("button", { name: "Move" }));

        expect(moveCategory).toHaveBeenCalledExactlyOnceWith(2, 3, [2], {
            goalTarget: 750000,
            goalTargetDate: "2027-06-01",
            goalStatus: "active",
        });
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });

    it("accepts a comma-decimal target without a deadline", async () => {
        seed({
            groups: [
                { id: 2, name: "Spending", kind: "expense", sort: 1 },
                { id: 3, name: "Plans", kind: "goal", sort: 2 },
            ],
            categories: [{ id: 2, groupId: 2, name: "Vacation", keywords: "", sort: 1 }],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container, user } = renderUI(<CategoriesPage />);
        dragCardToGroup(container, 2, 3);

        await user.type(screen.getByLabelText("Target, ₽"), "12,34");
        await user.click(screen.getByRole("button", { name: "Move" }));

        expect(moveCategory).toHaveBeenCalledWith(2, 3, [2], {
            goalTarget: 1234,
            goalTargetDate: null,
            goalStatus: "active",
        });
    });

    it.each([".", ",", "0", "-1", "999999999999999999999999"])(
        "rejects invalid goal target %s",
        async (value) => {
            seed({
                groups: [
                    { id: 2, name: "Spending", kind: "expense", sort: 1 },
                    { id: 3, name: "Plans", kind: "goal", sort: 2 },
                ],
                categories: [{ id: 2, groupId: 2, name: "Vacation", keywords: "", sort: 1 }],
            });
            const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
            const { container, user } = renderUI(<CategoriesPage />);
            dragCardToGroup(container, 2, 3);

            await user.type(screen.getByLabelText("Target, ₽"), value);

            expect(screen.getByRole("button", { name: "Move" })).toBeDisabled();
            expect(moveCategory).not.toHaveBeenCalled();
        },
    );

    it("keeps the goal prompt open when persisting the move fails", async () => {
        seed({
            groups: [
                { id: 2, name: "Spending", kind: "expense", sort: 1 },
                { id: 3, name: "Plans", kind: "goal", sort: 2 },
            ],
            categories: [{ id: 2, groupId: 2, name: "Vacation", keywords: "", sort: 1 }],
        });
        vi.spyOn(useStore.getState(), "moveCategory").mockRejectedValue(new Error("offline"));
        const { container, user } = renderUI(<CategoriesPage />);
        dragCardToGroup(container, 2, 3);
        await user.type(screen.getByLabelText("Target, ₽"), "100");
        await user.click(screen.getByRole("button", { name: "Move" }));

        expect(screen.getByRole("dialog")).toHaveTextContent("Set a goal for Vacation");
    });

    it("builds goal ordering from the latest category snapshot", async () => {
        seed({
            groups: [
                { id: 2, name: "Spending", kind: "expense", sort: 1 },
                { id: 3, name: "Plans", kind: "goal", sort: 2 },
            ],
            categories: [{ id: 2, groupId: 2, name: "Vacation", keywords: "", sort: 1 }],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container, user } = renderUI(<CategoriesPage />);
        dragCardToGroup(container, 2, 3);
        const snapshot = useStore.getState().snapshot;
        if (!snapshot) throw new Error("test snapshot is not loaded");
        useStore.setState({
            snapshot: {
                ...snapshot,
                groups: [...snapshot.groups, { id: 4, name: "Later", kind: "goal", sort: 3 }],
                categories: [
                    {
                        id: 8,
                        groupId: 2,
                        name: "Food",
                        keywords: "",
                        sort: 2,
                        archived: false,
                    },
                    ...snapshot.categories,
                    {
                        id: 9,
                        groupId: 3,
                        name: "House",
                        keywords: "",
                        sort: 1,
                        archived: false,
                    },
                ],
            },
        });
        await user.type(screen.getByLabelText("Target, ₽"), "100");
        await user.click(screen.getByRole("button", { name: "Move" }));

        expect(moveCategory).toHaveBeenCalledWith(2, 3, [8, 2, 9], expect.any(Object));
    });

    it("clears goal metadata when a goal is dragged into an expense group", () => {
        seed({
            groups: [
                { id: 2, name: "Spending", kind: "expense", sort: 1 },
                { id: 3, name: "Plans", kind: "goal", sort: 2 },
            ],
            categories: [
                {
                    id: 2,
                    groupId: 3,
                    name: "Vacation",
                    keywords: "",
                    sort: 1,
                    goalTarget: 750000,
                    goalTargetDate: "2027-06-01",
                    goalStatus: "active",
                },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        dragCardToGroup(container, 2, 2);

        expect(moveCategory).toHaveBeenCalledWith(2, 2, [2]);
    });

    it("moves a category between expense groups without a goal prompt", () => {
        seed({
            groups: [
                { id: 2, name: "Needs", kind: "expense", sort: 1 },
                { id: 3, name: "Wants", kind: "expense", sort: 2 },
            ],
            categories: [{ id: 2, groupId: 2, name: "Dining", keywords: "", sort: 1 }],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);

        dragCardToGroup(container, 2, 3);

        expect(screen.queryByText(/Set a goal for/)).not.toBeInTheDocument();
        expect(moveCategory).toHaveBeenCalledWith(2, 3, [2]);
    });

    it("keeps the category in place when the goal prompt is cancelled", async () => {
        seed({
            groups: [
                { id: 2, name: "Spending", kind: "expense", sort: 1 },
                { id: 3, name: "Plans", kind: "goal", sort: 2 },
            ],
            categories: [
                { id: 2, groupId: 2, name: "Vacation", keywords: "", sort: 1, archived: false },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container, user } = renderUI(<CategoriesPage />);

        dragCardToGroup(container, 2, 3);
        await user.click(screen.getByRole("button", { name: "Cancel" }));

        expect(moveCategory).not.toHaveBeenCalled();
        expect(container.querySelector('[data-gid="2"] [data-id="2"]')).toBeInTheDocument();
    });

    it("moves an existing goal without prompting again", () => {
        seed({
            groups: [
                { id: 2, name: "Old plans", kind: "goal", sort: 1 },
                { id: 3, name: "New plans", kind: "goal", sort: 2 },
            ],
            categories: [
                {
                    id: 2,
                    groupId: 2,
                    name: "Vacation",
                    keywords: "",
                    sort: 1,
                    archived: false,
                    goalTarget: 750000,
                },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);

        dragCardToGroup(container, 2, 3);

        expect(screen.queryByText("Set a goal for Vacation")).not.toBeInTheDocument();
        expect(moveCategory).toHaveBeenCalledExactlyOnceWith(2, 3, [2]);
    });

    it.each([0, -1])("prompts when an existing goal target is %s", (goalTarget) => {
        seed({
            groups: [
                { id: 2, name: "Old plans", kind: "goal", sort: 1 },
                { id: 3, name: "New plans", kind: "goal", sort: 2 },
            ],
            categories: [
                {
                    id: 2,
                    groupId: 2,
                    name: "Vacation",
                    keywords: "",
                    sort: 1,
                    archived: false,
                    goalTarget,
                },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);

        dragCardToGroup(container, 2, 3);

        expect(screen.getByText("Set a goal for Vacation")).toBeInTheDocument();
        expect(moveCategory).not.toHaveBeenCalled();
    });

    it("keeps the goal dialog open if its destination disappears", async () => {
        seed({
            groups: [
                { id: 2, name: "Spending", kind: "expense", sort: 1 },
                { id: 3, name: "Plans", kind: "goal", sort: 2 },
            ],
            categories: [
                { id: 2, groupId: 2, name: "Vacation", keywords: "", sort: 1, archived: false },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container, user } = renderUI(<CategoriesPage />);
        dragCardToGroup(container, 2, 3);
        const snapshot = useStore.getState().snapshot!;
        useStore.setState({ snapshot: { ...snapshot, groups: snapshot.groups.slice(0, 1) } });
        await user.type(screen.getByLabelText("Target, ₽"), "100");
        await user.click(screen.getByRole("button", { name: "Move" }));

        expect(screen.getByRole("dialog")).toHaveTextContent("Set a goal for Vacation");
        expect(moveCategory).not.toHaveBeenCalled();
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
        const source = container.querySelector<HTMLElement>('[data-id="2"]')!;
        const sourceGroup = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        const destination = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        source.getBoundingClientRect = () =>
            DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
        sourceGroup.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        destination.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 100,
                y: 0,
                width: 120,
                height: 200,
            });
        destination.querySelector<HTMLElement>('[data-id="3"]')!.getBoundingClientRect = () =>
            DOMRect.fromRect({
                y: 50,
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
                    ...container
                        .querySelector<HTMLElement>('[data-gid="3"]')!
                        .querySelectorAll<HTMLElement>(".kb-card__name"),
                ].map((card) => card.textContent),
            ).toEqual(["Groceries", "Rent"]),
        );
        expect(container.querySelector<HTMLElement>('[data-id="2"]')!).toHaveClass("kb-card_ghost");
    });

    it("reorders a dragged group and cancels a drag with Escape", () => {
        Object.defineProperty(HTMLElement.prototype, "animate", {
            configurable: true,
            value: () => ({ cancel: () => {} }),
        });
        seed({ groups, categories: [] });
        const reorderGroups = vi.spyOn(useStore.getState(), "reorderGroups").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const income = container.querySelector<HTMLElement>('[data-gid="1"]')!;
        const spending = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        income.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                width: 100,
                y: 0,
                height: 100,
            });
        spending.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 110,
                width: 100,
                y: 0,
                height: 100,
            });
        const head = income.querySelector<HTMLElement>(".kb-col__head")!;
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

        const tagOf = (gid: number) =>
            container.querySelector<HTMLElement>(`[data-gid="${gid}"] .kb-col__head .tag`)!;
        expect(tagOf(1)).toHaveTextContent("income");
        expect(tagOf(1)).toHaveClass("tag_success");
        expect(tagOf(2)).toHaveTextContent("expense");
        expect(tagOf(2)).toHaveClass("tag_danger");
        expect(tagOf(3)).toHaveTextContent("goal");
        expect(tagOf(3)).toHaveClass("tag_info");

        const countOf = (gid: number) =>
            container.querySelector<HTMLElement>(`[data-gid="${gid}"] .kb-col__count`)!.textContent;
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
        expect(
            container.querySelector<HTMLElement>('[data-gid="2"] .kb-add-card')!.textContent,
        ).toContain("Add category");
        expect(
            container.querySelector<HTMLElement>('[data-gid="3"] .kb-add-card')!.textContent,
        ).toContain("Add goal");
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

        const car = container.querySelector<HTMLElement>('[data-id="5"]')!;
        expect(car.querySelector<HTMLElement>(".kb-card__top .tag")!).toHaveTextContent("open");
        expect(car.querySelector<HTMLElement>(".kb-card__top .tag")!).toHaveClass("tag_success");
        expect(car.querySelector<HTMLElement>(".kb-card__goal")!.textContent).toMatch(
            /^Target\s1 500 000\s₽\s·\s2027-01-01$/,
        );

        const trip = container.querySelector<HTMLElement>('[data-id="6"]')!;
        expect(trip.querySelector<HTMLElement>(".kb-card__top .tag")!).toHaveTextContent("closed");
        expect(trip.querySelector<HTMLElement>(".kb-card__top .tag")!).toHaveClass("tag_warning");
        expect(trip.querySelector<HTMLElement>(".kb-card__goal")!.textContent).toBe("Target 50 ₽");
        expect(trip.querySelector<HTMLElement>(".kb-card__goal")!.textContent).not.toContain("·");
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
        const card = document.querySelector<HTMLElement>('[data-id="5"]')!;
        await user.click(card.querySelector<HTMLElement>(".kb-card__menu button")!);
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
        const card = document.querySelector<HTMLElement>('[data-id="5"]')!;
        await user.click(card.querySelector<HTMLElement>(".kb-card__menu button")!);
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
        const card = document.querySelector<HTMLElement>('[data-id="2"]')!;
        await user.click(card.querySelector<HTMLElement>(".kb-card__menu button")!);
        await user.click(await screen.findByRole("menuitem", { name: "Edit" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("Edit Food");
    });

    it("opens the group rename form from the group row menu", async () => {
        seed({ groups, categories: [] });
        const { user } = renderUI(<CategoriesPage />);
        const group = document.querySelector<HTMLElement>('[data-gid="2"]')!;
        await user.click(group.querySelector<HTMLElement>(".kb-col__head button")!);
        await user.click(await screen.findByRole("menuitem", { name: "Rename & kind" }));
        expect(screen.getByRole("dialog")).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Cancel" }));
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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
        expect(
            container.querySelector<HTMLElement>('[data-id="2"] .kb-card__kw')!.textContent,
        ).toBe("market, cafe");
        expect(container.querySelector<HTMLElement>('[data-id="3"] .kb-card__kw')!).toBeNull();
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
        const usage = container.querySelector<HTMLElement>('[data-id="2"] .kb-card__usage')!;
        expect(usage.textContent).toBe("3");
        expect(usage).toHaveAttribute("title", "3 transactions");
        expect(
            container.querySelector<HTMLElement>('[data-id="2"] .kb-card__top .tag')!,
        ).toBeNull();
    });

    it("renders income, expense and goal halves in both new-group controls", () => {
        seed({ groups, categories: [] });
        const { container } = renderUI(<CategoriesPage />);
        expect(
            [...container.querySelectorAll<HTMLElement>(".kb-newgroup__half")].map(
                (b) => b.textContent,
            ),
        ).toEqual(["Income", "Expense", "Goals"]);
        expect(
            [...container.querySelectorAll<HTMLElement>(".kb-col_add__half")].map((b) =>
                b.textContent.trim(),
            ),
        ).toEqual(["Income group", "Expense group", "Goals group"]);
    });

    it("starts a goal group from the new-group column goal half", async () => {
        seed({ groups, categories: [] });
        const { user, container } = renderUI(<CategoriesPage />);
        await user.click(container.querySelector<HTMLElement>(".kb-col_add__half_goal")!);
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
        const card = container.querySelector<HTMLElement>('[data-id="2"]')!;
        card.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
        container.querySelector<HTMLElement>('[data-gid="2"]')!.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        fireEvent.pointerDown(card, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 40, clientY: 40 });

        expect(container.querySelector<HTMLElement>('[data-id="2"]')!).toHaveClass("kb-card_ghost");
        expect(container.querySelector<HTMLElement>('[data-id="3"]')!).not.toHaveClass(
            "kb-card_ghost",
        );
        const clone = container.querySelector<HTMLElement>(".kb-card_clone")!;
        expect(clone).toHaveTextContent("Food");
        expect(clone.querySelector<HTMLElement>(".kb-card__usage")!.textContent).toBe("2");
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
        const card = container.querySelector<HTMLElement>('[data-id="2"]')!;
        fireEvent.pointerDown(card, { button: 1, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 40, clientY: 40 });
        fireEvent.pointerUp(window);
        expect(moveCategory).not.toHaveBeenCalled();
        expect(container.querySelector<HTMLElement>('[data-id="2"]')!).not.toHaveClass(
            "kb-card_ghost",
        );
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
        const card = container.querySelector<HTMLElement>('[data-id="2"]')!;
        fireEvent.pointerDown(card, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 12, clientY: 12 });
        fireEvent.pointerUp(window);
        expect(moveCategory).not.toHaveBeenCalled();
        expect(container.querySelector<HTMLElement>('[data-id="2"]')!).not.toHaveClass(
            "kb-card_ghost",
        );
    });

    it("positions the drag-layer clone at the pointer minus the grab offset", () => {
        vi.stubGlobal("requestAnimationFrame", () => 1);
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
            ],
        });
        vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const card = container.querySelector<HTMLElement>('[data-id="2"]')!;
        card.getBoundingClientRect = () => DOMRect.fromRect({ x: 4, y: 7, width: 80, height: 30 });
        container.querySelector<HTMLElement>('[data-gid="2"]')!.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        fireEvent.pointerDown(card, { button: 0, pointerType: "mouse", clientX: 30, clientY: 25 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 100, clientY: 90 });

        const layer = container.querySelector<HTMLElement>(".kb-drag-layer")!;
        expect(layer.style.left).toBe("74px");
        expect(layer.style.top).toBe("72px");
        expect(layer.style.width).toBe("80px");
        fireEvent.pointerUp(window);
    });

    it("drops a card after a taller target when the pointer clears its midpoint", () => {
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
        const source = container.querySelector<HTMLElement>('[data-id="2"]')!;
        const sourceGroup = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        const destination = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        const destinationCards = destination.querySelector<HTMLElement>(".kb-cards")!;
        source.getBoundingClientRect = () =>
            DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
        sourceGroup.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        destination.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 100,
                y: 0,
                width: 120,
                height: 200,
            });
        destinationCards.querySelector<HTMLElement>('[data-id="3"]')!.getBoundingClientRect = () =>
            DOMRect.fromRect({
                y: 50,
                height: 30,
            });

        fireEvent.pointerDown(source, {
            button: 0,
            pointerType: "mouse",
            clientX: 10,
            clientY: 10,
        });
        // pointer y=70 is below Rent's midpoint (50 + 30/2 = 65), so Groceries lands after it
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 150, clientY: 70 });
        fireEvent.pointerUp(window);

        expect(moveCategory).toHaveBeenCalledWith(2, 3, [3, 2]);
    });

    it("drops a card before the target when the pointer is above its midpoint", () => {
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
        const source = container.querySelector<HTMLElement>('[data-id="2"]')!;
        const sourceGroup = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        const destination = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        const destinationCards = destination.querySelector<HTMLElement>(".kb-cards")!;
        source.getBoundingClientRect = () =>
            DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
        sourceGroup.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        destination.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 100,
                y: 0,
                width: 120,
                height: 200,
            });
        destinationCards.querySelector<HTMLElement>('[data-id="3"]')!.getBoundingClientRect = () =>
            DOMRect.fromRect({
                y: 50,
                height: 30,
            });

        fireEvent.pointerDown(source, {
            button: 0,
            pointerType: "mouse",
            clientX: 10,
            clientY: 10,
        });
        // pointer y=60 is above Rent's midpoint (65), so Groceries lands before it
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 150, clientY: 60 });
        fireEvent.pointerUp(window);

        expect(moveCategory).toHaveBeenCalledWith(2, 3, [2, 3]);
    });

    it("picks the horizontally nearest column by edge distance", () => {
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
        const source = container.querySelector<HTMLElement>('[data-id="2"]')!;
        const sourceGroup = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        const destination = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        source.getBoundingClientRect = () =>
            DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
        sourceGroup.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        destination.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 100,
                y: 0,
                width: 120,
                height: 200,
            });

        fireEvent.pointerDown(source, {
            button: 0,
            pointerType: "mouse",
            clientX: 10,
            clientY: 10,
        });
        // x=95 is 15px right of source (right=80) and 5px left of destination (left=100):
        // destination is nearer, so the card lands there.
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 95, clientY: 10 });
        fireEvent.pointerUp(window);

        expect(moveCategory).toHaveBeenCalledWith(2, 3, [2, 3]);
    });

    it("keeps a card in its own column when the pointer stays inside it", () => {
        vi.stubGlobal("requestAnimationFrame", () => 1);
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        seed({
            groups: [
                { id: 2, name: "Food", kind: "expense", sort: 1 },
                { id: 3, name: "Home", kind: "expense", sort: 2 },
            ],
            categories: [
                { id: 2, groupId: 2, name: "Groceries", keywords: "", sort: 1, archived: false },
                { id: 4, groupId: 2, name: "Snacks", keywords: "", sort: 2, archived: false },
                { id: 3, groupId: 3, name: "Rent", keywords: "", sort: 1, archived: false },
            ],
        });
        const moveCategory = vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const source = container.querySelector<HTMLElement>('[data-id="2"]')!;
        const sourceGroup = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        const destination = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        const sourceCards = sourceGroup.querySelector<HTMLElement>(".kb-cards")!;
        source.getBoundingClientRect = () =>
            DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
        sourceGroup.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        destination.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 100,
                y: 0,
                width: 120,
                height: 200,
            });
        sourceCards.querySelector<HTMLElement>('[data-id="4"]')!.getBoundingClientRect = () =>
            DOMRect.fromRect({
                y: 50,
                height: 30,
            });

        fireEvent.pointerDown(source, {
            button: 0,
            pointerType: "mouse",
            clientX: 10,
            clientY: 10,
        });
        // x=40 is inside the source column (dist 0), y=70 is below Snacks' midpoint (65)
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 40, clientY: 70 });
        fireEvent.pointerUp(window);

        expect(moveCategory).toHaveBeenCalledWith(2, 2, [4, 2, 3]);
    });

    it("inserts a dragged group before a target once the pointer crosses its midline", () => {
        Object.defineProperty(HTMLElement.prototype, "animate", {
            configurable: true,
            value: () => ({ cancel: () => {} }),
        });
        seed({
            groups: [
                { id: 1, name: "Income", kind: "income", sort: 1 },
                { id: 2, name: "Spending", kind: "expense", sort: 2 },
                { id: 3, name: "Goals", kind: "goal", sort: 3 },
            ],
            categories: [],
        });
        const reorderGroups = vi.spyOn(useStore.getState(), "reorderGroups").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const income = container.querySelector<HTMLElement>('[data-gid="1"]')!;
        const spending = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        const goals = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        income.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                width: 100,
                y: 0,
                height: 100,
            });
        spending.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 110,
                width: 100,
                y: 0,
                height: 100,
            });
        goals.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 220,
                width: 100,
                y: 0,
                height: 100,
            });
        const head = income.querySelector<HTMLElement>(".kb-col__head")!;
        fireEvent.pointerDown(head, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        // dragging Income; others are Spending [110,210] and Goals [220,320].
        // x=270 is past Goals' midline (220 + 100/2 = 270 boundary), so Income lands last.
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 300, clientY: 20 });
        fireEvent.pointerUp(window);
        expect(reorderGroups).toHaveBeenCalledWith([2, 3, 1]);
    });

    it("inserts a dragged group between neighbours at the crossed midline", () => {
        Object.defineProperty(HTMLElement.prototype, "animate", {
            configurable: true,
            value: () => ({ cancel: () => {} }),
        });
        seed({
            groups: [
                { id: 1, name: "Income", kind: "income", sort: 1 },
                { id: 2, name: "Spending", kind: "expense", sort: 2 },
                { id: 3, name: "Goals", kind: "goal", sort: 3 },
            ],
            categories: [],
        });
        const reorderGroups = vi.spyOn(useStore.getState(), "reorderGroups").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const income = container.querySelector<HTMLElement>('[data-gid="1"]')!;
        const spending = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        const goals = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        income.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                width: 100,
                y: 0,
                height: 100,
            });
        spending.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 110,
                width: 100,
                y: 0,
                height: 100,
            });
        goals.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 220,
                width: 100,
                y: 0,
                height: 100,
            });
        const head = income.querySelector<HTMLElement>(".kb-col__head")!;
        fireEvent.pointerDown(head, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        // others: Spending [110,210], Goals [220,320]. x=250 is past Spending's midline (160)
        // but before Goals' midline (270), so Income lands between them.
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 250, clientY: 20 });
        fireEvent.pointerUp(window);
        expect(reorderGroups).toHaveBeenCalledWith([2, 1, 3]);
    });

    it("does not persist a reorder when Escape aborts the group drag", () => {
        Object.defineProperty(HTMLElement.prototype, "animate", {
            configurable: true,
            value: () => ({ cancel: () => {} }),
        });
        seed({ groups, categories: [] });
        const reorderGroups = vi.spyOn(useStore.getState(), "reorderGroups").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const income = container.querySelector<HTMLElement>('[data-gid="1"]')!;
        const spending = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        income.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                width: 100,
                y: 0,
                height: 100,
            });
        spending.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 110,
                width: 100,
                y: 0,
                height: 100,
            });
        const head = income.querySelector<HTMLElement>(".kb-col__head")!;
        fireEvent.pointerDown(head, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 180, clientY: 20 });
        expect(document.body).toHaveClass("kb-grabbing");
        fireEvent.keyDown(window, { key: "Enter" });
        expect(document.body).toHaveClass("kb-grabbing");
        fireEvent.keyDown(window, { key: "Escape" });
        expect(document.body).not.toHaveClass("kb-grabbing");
        fireEvent.pointerUp(window);
        expect(reorderGroups).not.toHaveBeenCalled();
    });

    it("shows only the card clone while dragging a card, not a column clone", () => {
        vi.stubGlobal("requestAnimationFrame", () => 1);
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                { id: 2, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
            ],
        });
        vi.spyOn(useStore.getState(), "moveCategory").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const card = container.querySelector<HTMLElement>('[data-id="2"]')!;
        card.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
        container.querySelector<HTMLElement>('[data-gid="2"]')!.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        fireEvent.pointerDown(card, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 40, clientY: 40 });

        expect(container.querySelector<HTMLElement>(".kb-card_clone")!).toBeInTheDocument();
        expect(container.querySelector<HTMLElement>(".kb-col_clone")!).toBeNull();
        fireEvent.pointerUp(window);
    });

    it("shows only the column clone with its cards while dragging a column", () => {
        vi.stubGlobal("requestAnimationFrame", () => 1);
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        Object.defineProperty(HTMLElement.prototype, "animate", {
            configurable: true,
            value: () => ({ cancel: () => {} }),
        });
        seed({
            groups: [
                { id: 1, name: "Income", kind: "income", sort: 1 },
                { id: 2, name: "Spending", kind: "expense", sort: 2 },
            ],
            categories: [
                { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
                { id: 2, groupId: 1, name: "Bonus", keywords: "", sort: 2, archived: false },
            ],
        });
        vi.spyOn(useStore.getState(), "reorderGroups").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const income = container.querySelector<HTMLElement>('[data-gid="1"]')!;
        const spending = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        income.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                width: 100,
                y: 0,
                height: 100,
            });
        spending.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 110,
                width: 100,
                y: 0,
                height: 100,
            });
        const head = income.querySelector<HTMLElement>(".kb-col__head")!;
        fireEvent.pointerDown(head, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 40, clientY: 20 });

        const clone = container.querySelector<HTMLElement>(".kb-col_clone")!;
        expect(clone).toBeInTheDocument();
        expect(container.querySelector<HTMLElement>(".kb-card_clone")!).toBeNull();
        // the column clone carries the group's own kind theme and category count
        expect(clone).toHaveClass("kb-col_income");
        expect(clone.querySelector<HTMLElement>(".kb-col__count")!.textContent).toBe("2");
        expect(
            [...clone.querySelectorAll<HTMLElement>(".kb-card__name")].map((el) => el.textContent),
        ).toEqual(["Salary", "Bonus"]);
        fireEvent.pointerUp(window);
    });

    it("colours the dragged column clone tag by its kind", () => {
        vi.stubGlobal("requestAnimationFrame", () => 1);
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        Object.defineProperty(HTMLElement.prototype, "animate", {
            configurable: true,
            value: () => ({ cancel: () => {} }),
        });
        seed({
            groups: [
                { id: 3, name: "Goals", kind: "goal", sort: 1 },
                { id: 2, name: "Spending", kind: "expense", sort: 2 },
            ],
            categories: [],
        });
        vi.spyOn(useStore.getState(), "reorderGroups").mockResolvedValue();
        const { container } = renderUI(<CategoriesPage />);
        const goals = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        const spending = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        goals.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                width: 100,
                y: 0,
                height: 100,
            });
        spending.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 110,
                width: 100,
                y: 0,
                height: 100,
            });
        const head = goals.querySelector<HTMLElement>(".kb-col__head")!;
        fireEvent.pointerDown(head, { button: 0, pointerType: "mouse", clientX: 10, clientY: 10 });
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 40, clientY: 20 });

        const clone = container.querySelector<HTMLElement>(".kb-col_clone")!;
        expect(clone.querySelector<HTMLElement>(".tag")!).toHaveTextContent("goal");
        expect(clone.querySelector<HTMLElement>(".tag")!).toHaveClass("tag_info");
        fireEvent.pointerUp(window);
    });

    it("keeps the drop indicator anchored to the hovered slot across a jitter move", async () => {
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
        const source = container.querySelector<HTMLElement>('[data-id="2"]')!;
        const sourceGroup = container.querySelector<HTMLElement>('[data-gid="2"]')!;
        const destination = container.querySelector<HTMLElement>('[data-gid="3"]')!;
        source.getBoundingClientRect = () =>
            DOMRect.fromRect({ x: 0, y: 0, width: 80, height: 30 });
        sourceGroup.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 0,
                y: 0,
                width: 80,
                height: 200,
            });
        destination.getBoundingClientRect = () =>
            DOMRect.fromRect({
                x: 100,
                y: 0,
                width: 120,
                height: 200,
            });
        destination.querySelector<HTMLElement>('[data-id="3"]')!.getBoundingClientRect = () =>
            DOMRect.fromRect({
                y: 50,
                height: 30,
            });

        fireEvent.pointerDown(source, {
            button: 0,
            pointerType: "mouse",
            clientX: 10,
            clientY: 10,
        });
        // land it below Rent's midpoint so the ghost slot follows Rent
        fireEvent.pointerMove(window, { pointerType: "mouse", clientX: 150, clientY: 70 });

        await waitFor(() =>
            expect(
                [
                    ...container
                        .querySelector<HTMLElement>('[data-gid="3"]')!
                        .querySelectorAll<HTMLElement>(".kb-card__name"),
                ].map((card) => card.textContent),
            ).toEqual(["Rent", "Groceries"]),
        );
    });
});
