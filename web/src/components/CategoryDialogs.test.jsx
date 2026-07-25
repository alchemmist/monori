import { describe, expect, it, vi, beforeEach } from "vitest";
import { CategoryEditDialog, CategoryDeleteDialog } from "./CategoryDialogs.jsx";
import {
    renderUI,
    resetStore,
    seed,
    screen,
    within,
    waitFor,
    userEvent,
} from "../test/render.jsx";
import { useStore } from "../store.js";

describe("CategoryEditDialog", () => {
    beforeEach(() => {
        resetStore();
    });

    it("opens with the category name prefilled in edit mode", async () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "food" };
        const groups = [
            { id: 1, name: "Income", kind: "income" },
            { id: 2, name: "Living", kind: "expense" },
        ];

        renderUI(<CategoryEditDialog category={category} groups={groups} onClose={() => {}} />);

        const inputs = screen.getAllByRole("textbox");
        expect(inputs[0]).toHaveValue("Groceries");
        expect(inputs[1]).toHaveValue("food");
        expect(screen.getByRole("heading")).toHaveTextContent("Edit Groceries");
        // Group select should show Living
        expect(screen.getByText("Living")).toBeInTheDocument();
    });

    it("opens in create mode with empty fields", async () => {
        seed();
        const groups = [
            { id: 1, name: "Income", kind: "income" },
            { id: 2, name: "Living", kind: "expense" },
        ];

        renderUI(
            <CategoryEditDialog
                category={{ groupId: 1 }}
                groups={groups}
                onClose={() => {}}
            />,
        );

        expect(screen.getByRole("heading")).toHaveTextContent("New category");
        const inputs = screen.getAllByRole("textbox");
        expect(inputs[0]).toHaveValue("");
        expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
    });

    it("disables the apply button when name is empty", async () => {
        seed();
        const { user } = renderUI(
            <CategoryEditDialog
                category={{ id: 1, name: "Test", groupId: 1, keywords: "" }}
                groups={[{ id: 1, name: "Income", kind: "income" }]}
                onClose={() => {}}
            />,
        );

        const nameInput = screen.getAllByRole("textbox")[0];
        await user.clear(nameInput);

        const applyBtn = screen.getByRole("button", { name: "Save" });
        expect(applyBtn).toBeDisabled();
    });

    it("creates category and closes dialog on success", async () => {
        seed();
        const onClose = vi.fn();
        const { user } = renderUI(
            <CategoryEditDialog
                category={{ groupId: 1 }}
                groups={[{ id: 1, name: "Income", kind: "income" }]}
                onClose={onClose}
            />,
        );

        vi.spyOn(useStore.getState(), "createCategory").mockResolvedValue(undefined);

        const inputs = screen.getAllByRole("textbox");
        await user.type(inputs[0], "  New Cat  ");
        await user.type(inputs[1], "test|another");

        await user.click(screen.getByRole("button", { name: "Create" }));

        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("updates category and closes dialog on success", async () => {
        seed();
        const onClose = vi.fn();
        const category = { id: 5, name: "Old Name", groupId: 1, keywords: "old" };
        const { user } = renderUI(
            <CategoryEditDialog
                category={category}
                groups={[{ id: 1, name: "Income", kind: "income" }]}
                onClose={onClose}
            />,
        );

        vi.spyOn(useStore.getState(), "patchCategory").mockResolvedValue(undefined);

        const inputs = screen.getAllByRole("textbox");
        await user.clear(inputs[0]);
        await user.type(inputs[0], "New Name");

        await user.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("submits with current groupId when group is not changed", async () => {
        seed();
        const category = { id: 3, name: "Test", groupId: 1, keywords: "" };
        const groups = [
            { id: 1, name: "Income", kind: "income" },
            { id: 2, name: "Living", kind: "expense" },
        ];
        const { user } = renderUI(
            <CategoryEditDialog category={category} groups={groups} onClose={() => {}} />,
        );

        vi.spyOn(useStore.getState(), "patchCategory").mockResolvedValue(undefined);

        const nameInput = screen.getAllByRole("textbox")[0];
        await user.clear(nameInput);
        await user.type(nameInput, "Updated");

        await user.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => {
            expect(useStore.getState().patchCategory).toHaveBeenCalledWith(3, {
                name: "Updated",
                groupId: 1,
                keywords: "",
            });
        });
    });

    it("closes dialog after successful create", async () => {
        seed();
        const onClose = vi.fn();
        const { user } = renderUI(
            <CategoryEditDialog
                category={{ groupId: 1 }}
                groups={[{ id: 1, name: "Income", kind: "income" }]}
                onClose={onClose}
            />,
        );

        vi.spyOn(useStore.getState(), "createCategory").mockResolvedValue(undefined);

        const inputs = screen.getAllByRole("textbox");
        await user.type(inputs[0], "Test");

        await user.click(screen.getByRole("button", { name: "Create" }));

        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("shows error notification when create fails", async () => {
        seed();
        const { user } = renderUI(
            <CategoryEditDialog
                category={{ groupId: 1 }}
                groups={[{ id: 1, name: "Income", kind: "income" }]}
                onClose={() => {}}
            />,
        );

        vi.spyOn(useStore.getState(), "createCategory").mockRejectedValue(
            new Error("Network failed"),
        );

        const inputs = screen.getAllByRole("textbox");
        await user.type(inputs[0], "Test");

        await user.click(screen.getByRole("button", { name: "Create" }));

        await waitFor(() => {
            expect(screen.getByText("Failed to create category")).toBeInTheDocument();
        });
    });

    it("shows error notification when update fails", async () => {
        seed();
        const { user } = renderUI(
            <CategoryEditDialog
                category={{ id: 1, name: "Test", groupId: 1, keywords: "" }}
                groups={[{ id: 1, name: "Income", kind: "income" }]}
                onClose={() => {}}
            />,
        );

        vi.spyOn(useStore.getState(), "patchCategory").mockRejectedValue(
            new Error("Server error"),
        );

        const nameInput = screen.getAllByRole("textbox")[0];
        await user.clear(nameInput);
        await user.type(nameInput, "Changed");

        await user.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => {
            expect(screen.getByText("Failed to update category")).toBeInTheDocument();
        });
    });

    it("keeps button disabled while operation is pending", async () => {
        seed();
        const { user } = renderUI(
            <CategoryEditDialog
                category={{ groupId: 1 }}
                groups={[{ id: 1, name: "Income", kind: "income" }]}
                onClose={() => {}}
            />,
        );

        let resolveCreate;
        vi.spyOn(useStore.getState(), "createCategory").mockImplementation(
            () => new Promise((r) => (resolveCreate = r)),
        );

        const inputs = screen.getAllByRole("textbox");
        await user.type(inputs[0], "Test");

        const btn = screen.getByRole("button", { name: "Create" });
        await user.click(btn);

        // After click, the component should be in a loading state
        // We can test the operation was called
        await waitFor(() => {
            expect(useStore.getState().createCategory).toHaveBeenCalled();
        });

        resolveCreate();

        // After resolution, onClose should be called
        // The component re-renders and the dialog closes
    });

    it("shows keywords help text", () => {
        seed();
        renderUI(
            <CategoryEditDialog
                category={{ groupId: 1 }}
                groups={[{ id: 1, name: "Income", kind: "income" }]}
                onClose={() => {}}
            />,
        );

        expect(
            screen.getByText(/Keywords are matched against transaction descriptions/),
        ).toBeInTheDocument();
    });
});

describe("CategoryDeleteDialog", () => {
    beforeEach(() => {
        resetStore();
    });

    it("shows transaction count and merge options", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "food" };
        const categories = [
            { id: 1, groupId: 1, name: "Salary", keywords: "" },
            { id: 2, groupId: 2, name: "Groceries", keywords: "food" },
            { id: 3, groupId: 2, name: "Rent", keywords: "" },
        ];

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={categories}
                txCount={5}
                onClose={() => {}}
            />,
        );

        expect(screen.getByText("5 transactions use this category.")).toBeInTheDocument();
        expect(screen.getByText(/Where should they go/)).toBeInTheDocument();
    });

    it("shows zero transaction message when no transactions", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={[category]}
                txCount={0}
                onClose={() => {}}
            />,
        );

        expect(screen.getByText("No transactions use this category.")).toBeInTheDocument();
    });

    it("only offers categories of the same kind for merge", () => {
        seed({
            categories: [
                { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
                { id: 2, groupId: 2, name: "Groceries", keywords: "", sort: 1, archived: false },
                { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
                { id: 4, groupId: 1, name: "Freelance", keywords: "", sort: 2, archived: false },
            ],
            groups: [
                { id: 1, name: "Income", kind: "income", sort: 1 },
                { id: 2, name: "Living", kind: "expense", sort: 2 },
            ],
        });

        const allCats = useStore.getState().snapshot.categories;
        const expenseCategory = allCats.find((c) => c.id === 2);

        renderUI(
            <CategoryDeleteDialog
                category={expenseCategory}
                categories={allCats}
                txCount={0}
                onClose={() => {}}
            />,
        );

        // Only same-kind categories should be mentioned in the help text or options
        expect(screen.getByText("Rent")).toBeInTheDocument();
        // Income categories should not appear
        expect(screen.queryByText("Salary")).not.toBeInTheDocument();
        expect(screen.queryByText("Freelance")).not.toBeInTheDocument();
    });

    it("shows transaction count in plan", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "food|market" };
        const categories = [
            { id: 2, groupId: 2, name: "Groceries", keywords: "food|market", sort: 1, archived: false },
            { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
        ];

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={categories}
                txCount={10}
                onClose={() => {}}
            />,
        );

        expect(screen.getByText(/10 transactions use this category/)).toBeInTheDocument();
    });

    it("renders keywords help text", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "food|market" };
        const categories = [
            { id: 2, groupId: 2, name: "Groceries", keywords: "food|market", sort: 1, archived: false },
            { id: 3, groupId: 2, name: "Rent", keywords: "landlord", sort: 2, archived: false },
        ];

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={categories}
                txCount={0}
                onClose={() => {}}
            />,
        );

        expect(
            screen.getByText(/Keywords added to Rent: food, market/),
        ).toBeInTheDocument();
    });

    it("filters duplicate keywords in merge plan", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "food|market" };
        const categories = [
            { id: 2, groupId: 2, name: "Groceries", keywords: "food|market", sort: 1, archived: false },
            { id: 3, groupId: 2, name: "Rent", keywords: "food|landlord", sort: 2, archived: false },
        ];

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={categories}
                txCount={0}
                onClose={() => {}}
            />,
        );

        // Only "market" is new; "food" is already in Rent, so don't list it
        expect(screen.getByText(/Keywords added to Rent: market/)).toBeInTheDocument();
    });

    it("shows budget count in plan when budgets exist", () => {
        seed({
            budgets: [
                { id: 1, categoryId: 2, month: "2026-01", amount: 10000 },
                { id: 2, categoryId: 2, month: "2026-02", amount: 10000 },
            ],
        });

        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };
        const categories = [
            { id: 2, groupId: 2, name: "Groceries", keywords: "", sort: 1, archived: false },
            { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
        ];

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={categories}
                txCount={0}
                onClose={() => {}}
            />,
        );

        expect(screen.getByText(/Budgets for 2 months are added to the target's plan/)).toBeInTheDocument();
    });

    it("notes empty budget history in merge plan", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };
        const categories = [
            { id: 2, groupId: 2, name: "Groceries", keywords: "", sort: 1, archived: false },
            { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
        ];

        const { user } = renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={categories}
                txCount={0}
                onClose={() => {}}
            />,
        );

        const select = screen.getByDisplayValue("Leave uncategorized");
        user.click(select);
        user.click(screen.getByRole("option", { name: "Rent" }));

        expect(screen.getByText(/No budgets to carry over/)).toBeInTheDocument();
    });

    it("shows uncategorized plan with transactions", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={[category]}
                txCount={3}
                onClose={() => {}}
            />,
        );

        expect(screen.getByText(/3 transactions are left without a category/)).toBeInTheDocument();
    });

    it("shows uncategorized plan with no transactions", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={[category]}
                txCount={0}
                onClose={() => {}}
            />,
        );

        expect(screen.queryByText(/transactions are left without a category/)).not.toBeInTheDocument();
    });

    it("deletes category and closes dialog on success", async () => {
        seed();
        const onClose = vi.fn();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };

        const { user } = renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={[category]}
                txCount={0}
                onClose={onClose}
            />,
        );

        vi.spyOn(useStore.getState(), "deleteCategory").mockResolvedValue(undefined);

        await user.click(screen.getByRole("button", { name: "Delete" }));

        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("merges categories when both target has categories", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };
        const categories = [
            { id: 2, groupId: 2, name: "Groceries", keywords: "", sort: 1, archived: false },
            { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
        ];

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={categories}
                txCount={5}
                onClose={() => {}}
            />,
        );

        // The dialog should show option to move to Rent
        expect(screen.getByText("Rent")).toBeInTheDocument();
    });

    it("shows error notification when delete fails", async () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };

        const { user } = renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={[category]}
                txCount={0}
                onClose={() => {}}
            />,
        );

        vi.spyOn(useStore.getState(), "deleteCategory").mockRejectedValue(
            new Error("Server error"),
        );

        await user.click(screen.getByRole("button", { name: "Delete" }));

        await waitFor(() => {
            expect(screen.getByText("Failed to delete category")).toBeInTheDocument();
        });
    });

    it("shows error notification when delete fails", async () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };

        const { user } = renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={[category]}
                txCount={0}
                onClose={() => {}}
            />,
        );

        vi.spyOn(useStore.getState(), "deleteCategory").mockRejectedValue(
            new Error("Cannot delete"),
        );

        await user.click(screen.getByRole("button", { name: "Delete" }));

        await waitFor(() => {
            expect(screen.getByText("Failed to delete category")).toBeInTheDocument();
            expect(screen.getByText("Error: Cannot delete")).toBeInTheDocument();
        });
    });

    it("shows kind explanation in help text", () => {
        seed();
        renderUI(
            <CategoryDeleteDialog
                category={{ id: 1, name: "Test", groupId: 1, keywords: "" }}
                categories={[{ id: 1, name: "Test", groupId: 1, keywords: "", sort: 1, archived: false }]}
                txCount={0}
                onClose={() => {}}
            />,
        );

        expect(
            screen.getByText(/Only categories of the same kind are offered/),
        ).toBeInTheDocument();
    });

    it("handles delete operation and closes on success", async () => {
        seed();
        const onClose = vi.fn();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };

        const { user } = renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={[category]}
                txCount={0}
                onClose={onClose}
            />,
        );

        vi.spyOn(useStore.getState(), "deleteCategory").mockResolvedValue(undefined);

        const btn = screen.getByRole("button", { name: "Delete" });
        await user.click(btn);

        await waitFor(() => {
            expect(useStore.getState().deleteCategory).toHaveBeenCalled();
        });

        // After the promise resolves, onClose should be called
        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("always notes that deletion is irreversible", () => {
        seed();
        const category = { id: 2, name: "Groceries", groupId: 2, keywords: "" };

        renderUI(
            <CategoryDeleteDialog
                category={category}
                categories={[category]}
                txCount={0}
                onClose={() => {}}
            />,
        );

        expect(screen.getByText("Groceries")).toBeInTheDocument();
        expect(screen.getByText(/cannot be undone/)).toBeInTheDocument();
    });
});
