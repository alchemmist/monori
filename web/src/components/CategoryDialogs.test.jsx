import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import { CategoryDeleteDialog, CategoryEditDialog } from "./CategoryDialogs.jsx";
import { GroupDeleteDialog, GroupEditDialog } from "./GroupDialogs.jsx";

const groups = [
    { id: 1, name: "Income", kind: "income", sort: 1 },
    { id: 2, name: "Home", kind: "expense", sort: 2 },
];
const food = { id: 2, groupId: 2, name: "Food", keywords: "shop|cafe", sort: 1 };
const rent = { id: 3, groupId: 2, name: "Rent", keywords: "cafe|home", sort: 2 };

describe("category and group dialogs", () => {
    beforeEach(() => {
        resetStore();
        seed({
            groups,
            categories: [food, rent],
            budgets: [{ categoryId: 2, year: 2026, month: 1, amount: 100 }],
        });
    });

    it("creates a category from the edit form", async () => {
        const create = vi.spyOn(useStore.getState(), "createCategory").mockResolvedValue(4);
        const close = vi.fn();
        const { user } = renderUI(
            <CategoryEditDialog category={{ groupId: 2 }} groups={groups} onClose={close} />,
        );
        await user.type(screen.getByLabelText("Name"), "Transport");
        await user.type(screen.getByLabelText("Keywords"), "taxi|metro");
        await user.click(screen.getByRole("button", { name: "Create" }));
        await waitFor(() =>
            expect(create).toHaveBeenCalledWith({
                name: "Transport",
                groupId: 2,
                keywords: "taxi|metro",
            }),
        );
        expect(close).toHaveBeenCalled();
    });

    it("explains an uncategorized delete and invokes delete", async () => {
        const remove = vi.spyOn(useStore.getState(), "deleteCategory").mockResolvedValue();
        const { user } = renderUI(
            <CategoryDeleteDialog
                category={food}
                categories={[food]}
                txCount={2}
                onClose={vi.fn()}
            />,
        );
        expect(screen.getByText(/2 transactions are left without a category/)).toBeInTheDocument();
        expect(screen.getByText(/Budgets for 1 month are removed/)).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(remove).toHaveBeenCalledWith(2));
    });

    it("merges into a same-kind target and spells out carried data", async () => {
        const merge = vi.spyOn(useStore.getState(), "mergeCategory").mockResolvedValue();
        const { user } = renderUI(
            <CategoryDeleteDialog
                category={food}
                categories={[food, rent]}
                txCount={1}
                onClose={vi.fn()}
            />,
        );
        await user.click(screen.getByRole("button", { name: /leave uncategorized/i }));
        await user.click(screen.getByText("Rent"));
        expect(screen.getByText(/1 transaction moves to Rent/)).toBeInTheDocument();
        // "cafe" is already on Rent, so the irreversible merge adds "shop" and nothing else
        expect(screen.getByText("Keywords added to Rent: shop")).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(merge).toHaveBeenCalledWith(2, 3));
    });

    it("edits groups and blocks deletion while categories remain", async () => {
        const patch = vi.spyOn(useStore.getState(), "patchGroup").mockResolvedValue();
        const { user } = renderUI(<GroupEditDialog group={groups[1]} onClose={vi.fn()} />);
        await user.clear(screen.getByLabelText("Name"));
        await user.type(screen.getByLabelText("Name"), "House");
        await user.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() =>
            expect(patch).toHaveBeenCalledWith(2, { name: "House", kind: "expense" }),
        );
        const { user: blocker } = renderUI(
            <GroupDeleteDialog group={groups[1]} catCount={1} onClose={vi.fn()} />,
        );
        expect(screen.getByText(/still holds 1 category/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
        await blocker.click(screen.getByRole("button", { name: "Delete" }));
    });

    it("creates an income group and closes only after the store resolves", async () => {
        const create = vi.spyOn(useStore.getState(), "createGroup").mockResolvedValue(5);
        const close = vi.fn();
        const { user } = renderUI(<GroupEditDialog group={{}} onClose={close} />);
        const apply = screen.getByRole("button", { name: "Create" });
        expect(apply).toBeDisabled();
        await user.type(screen.getByLabelText("Name"), " Paychecks ");
        await user.click(screen.getByText("Income"));
        await user.click(apply);
        await waitFor(() =>
            expect(create).toHaveBeenCalledWith({ name: "Paychecks", kind: "income" }),
        );
        expect(close).toHaveBeenCalledOnce();
    });

    it("reports group mutation failures and keeps the dialog open", async () => {
        const notify = vi.spyOn(useStore.getState(), "notify");
        vi.spyOn(useStore.getState(), "patchGroup").mockRejectedValue(new Error("offline"));
        const close = vi.fn();
        const { user } = renderUI(<GroupEditDialog group={groups[1]} onClose={close} />);
        await user.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Failed to update group", theme: "danger" }),
            ),
        );
        expect(close).not.toHaveBeenCalled();

        vi.spyOn(useStore.getState(), "deleteGroup").mockRejectedValue(new Error("offline"));
        renderUI(<GroupDeleteDialog group={groups[0]} catCount={0} onClose={close} />);
        expect(screen.getByText(/group is empty and will be removed/)).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Failed to delete group", theme: "danger" }),
            ),
        );
    });

    it("deletes an empty group", async () => {
        const remove = vi.spyOn(useStore.getState(), "deleteGroup").mockResolvedValue();
        const close = vi.fn();
        const { user } = renderUI(
            <GroupDeleteDialog group={groups[0]} catCount={0} onClose={close} />,
        );
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(remove).toHaveBeenCalledWith(1));
        expect(close).toHaveBeenCalledOnce();
    });
});
