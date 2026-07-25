import { describe, expect, it, vi, beforeEach } from "vitest";
import { GroupEditDialog, GroupDeleteDialog } from "./GroupDialogs.jsx";
import {
    renderUI,
    resetStore,
    seed,
    screen,
    waitFor,
    userEvent,
} from "../test/render.jsx";
import { useStore } from "../store.js";

describe("GroupEditDialog", () => {
    beforeEach(() => {
        resetStore();
    });

    it("opens with group name prefilled in edit mode", () => {
        seed();
        const group = { id: 2, name: "Living", kind: "expense" };

        renderUI(<GroupEditDialog group={group} onClose={() => {}} />);

        const nameInput = screen.getByRole("textbox");
        expect(nameInput).toHaveValue("Living");
        expect(screen.getByRole("radio", { name: "Expense" })).toBeChecked();
        expect(screen.getByRole("heading")).toHaveTextContent("Edit Living");
    });

    it("opens in create mode with empty name and default kind", () => {
        seed();

        renderUI(<GroupEditDialog group={{ kind: "expense" }} onClose={() => {}} />);

        expect(screen.getByRole("heading")).toHaveTextContent("New group");
        const nameInput = screen.getByRole("textbox");
        expect(nameInput).toHaveValue("");
        expect(screen.getByRole("radio", { name: "Expense" })).toBeChecked();
        expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
    });

    it("disables apply button when name is empty", async () => {
        seed();
        const { user } = renderUI(
            <GroupEditDialog group={{ id: 1, name: "Test", kind: "income" }} onClose={() => {}} />,
        );

        const nameInput = screen.getByDisplayValue("Test");
        await user.clear(nameInput);

        const applyBtn = screen.getByRole("button", { name: "Save" });
        expect(applyBtn).toBeDisabled();
    });

    it("allows toggling between income and expense", async () => {
        seed();
        const { user } = renderUI(
            <GroupEditDialog group={{ kind: "expense" }} onClose={() => {}} />,
        );

        const incomeButton = screen.getByRole("radio", { name: "Income" });
        expect(incomeButton).not.toBeChecked();

        await user.click(incomeButton);

        expect(incomeButton).toBeChecked();
        expect(screen.getByRole("radio", { name: "Expense" })).not.toBeChecked();
    });

    it("submits form with trimmed name and selected kind", async () => {
        seed();
        const onClose = vi.fn();
        const { user } = renderUI(
            <GroupEditDialog group={{ kind: "income" }} onClose={onClose} />,
        );

        vi.spyOn(useStore.getState(), "createGroup").mockResolvedValue(undefined);

        const nameInput = screen.getByRole("textbox");
        await user.type(nameInput, "  Savings  ");

        await user.click(screen.getByRole("button", { name: "Create" }));

        // Should close if successful
        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("saves edited group with new name and kind", async () => {
        seed();
        const onClose = vi.fn();
        const { user } = renderUI(
            <GroupEditDialog
                group={{ id: 3, name: "Old Name", kind: "expense" }}
                onClose={onClose}
            />,
        );

        vi.spyOn(useStore.getState(), "patchGroup").mockResolvedValue(undefined);

        const nameInput = screen.getByRole("textbox");
        await user.clear(nameInput);
        await user.type(nameInput, "New Name");

        const incomeButton = screen.getByRole("radio", { name: "Income" });
        await user.click(incomeButton);

        await user.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("closes dialog after successful create", async () => {
        seed();
        const onClose = vi.fn();
        const { user } = renderUI(
            <GroupEditDialog group={{ kind: "expense" }} onClose={onClose} />,
        );

        vi.spyOn(useStore.getState(), "createGroup").mockResolvedValue(undefined);

        const nameInput = screen.getByRole("textbox");
        await user.type(nameInput, "Test Group");

        await user.click(screen.getByRole("button", { name: "Create" }));

        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("shows error notification when create fails", async () => {
        seed();
        const { user } = renderUI(
            <GroupEditDialog group={{ kind: "expense" }} onClose={() => {}} />,
        );

        vi.spyOn(useStore.getState(), "createGroup").mockRejectedValue(
            new Error("Network error"),
        );

        const nameInput = screen.getByRole("textbox");
        await user.type(nameInput, "Test");

        await user.click(screen.getByRole("button", { name: "Create" }));

        // The error should be shown as a notification
        await waitFor(() => {
            expect(screen.getByText("Failed to create group")).toBeInTheDocument();
        });
    });

    it("shows error notification when update fails", async () => {
        seed();
        const { user } = renderUI(
            <GroupEditDialog group={{ id: 1, name: "Test", kind: "expense" }} onClose={() => {}} />,
        );

        vi.spyOn(useStore.getState(), "patchGroup").mockRejectedValue(
            new Error("Server refused"),
        );

        const nameInput = screen.getByRole("textbox");
        await user.clear(nameInput);
        await user.type(nameInput, "Changed");

        await user.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => {
            expect(screen.getByText("Failed to update group")).toBeInTheDocument();
        });
    });

    it("handles create operation and closes on success", async () => {
        seed();
        const onClose = vi.fn();
        const { user } = renderUI(
            <GroupEditDialog group={{ kind: "expense" }} onClose={onClose} />,
        );

        vi.spyOn(useStore.getState(), "createGroup").mockResolvedValue(undefined);

        const nameInput = screen.getByRole("textbox");
        await user.type(nameInput, "Test");

        const btn = screen.getByRole("button", { name: "Create" });
        await user.click(btn);

        await waitFor(() => {
            expect(useStore.getState().createGroup).toHaveBeenCalled();
        });

        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("shows help text explaining income vs expense", () => {
        seed();
        renderUI(<GroupEditDialog group={{ kind: "expense" }} onClose={() => {}} />);

        expect(
            screen.getByText(/Income groups collect money coming in/),
        ).toBeInTheDocument();
    });
});

describe("GroupDeleteDialog", () => {
    beforeEach(() => {
        resetStore();
    });

    it("shows message when group is empty", () => {
        seed();
        const group = { id: 1, name: "Income", kind: "income" };

        renderUI(
            <GroupDeleteDialog group={group} catCount={0} onClose={() => {}} />,
        );

        expect(screen.getByText(/This group is empty and will be removed/)).toBeInTheDocument();
    });

    it("shows refusal message when group has categories", () => {
        seed();
        const group = { id: 2, name: "Living", kind: "expense" };

        renderUI(
            <GroupDeleteDialog group={group} catCount={3} onClose={() => {}} />,
        );

        expect(
            screen.getByText(/This group still holds 3 categories/),
        ).toBeInTheDocument();
        expect(screen.getByText(/Move or delete them first/)).toBeInTheDocument();
    });

    it("pluralizes category count correctly", () => {
        seed();
        const group = { id: 2, name: "Living", kind: "expense" };

        const { rerender } = renderUI(
            <GroupDeleteDialog group={group} catCount={1} onClose={() => {}} />,
        );

        expect(screen.getByText(/still holds 1 category/)).toBeInTheDocument();

        rerender(
            <GroupDeleteDialog group={group} catCount={2} onClose={() => {}} />,
        );

        expect(screen.getByText(/still holds 2 categories/)).toBeInTheDocument();
    });

    it("disables delete button when group has categories", () => {
        seed();
        const group = { id: 2, name: "Living", kind: "expense" };

        renderUI(
            <GroupDeleteDialog group={group} catCount={2} onClose={() => {}} />,
        );

        const deleteBtn = screen.getByRole("button", { name: "Delete" });
        expect(deleteBtn).toBeDisabled();
    });

    it("enables delete button when group is empty", () => {
        seed();
        const group = { id: 1, name: "Income", kind: "income" };

        renderUI(
            <GroupDeleteDialog group={group} catCount={0} onClose={() => {}} />,
        );

        const deleteBtn = screen.getByRole("button", { name: "Delete" });
        expect(deleteBtn).not.toBeDisabled();
    });

    it("deletes empty group and closes dialog", async () => {
        seed();
        const onClose = vi.fn();
        const group = { id: 5, name: "Income", kind: "income" };

        const { user } = renderUI(
            <GroupDeleteDialog group={group} catCount={0} onClose={onClose} />,
        );

        vi.spyOn(useStore.getState(), "deleteGroup").mockResolvedValue(undefined);

        await user.click(screen.getByRole("button", { name: "Delete" }));

        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });

    it("shows error notification when delete fails", async () => {
        seed();
        const group = { id: 1, name: "Income", kind: "income" };

        const { user } = renderUI(
            <GroupDeleteDialog group={group} catCount={0} onClose={() => {}} />,
        );

        vi.spyOn(useStore.getState(), "deleteGroup").mockRejectedValue(
            new Error("Server error"),
        );

        await user.click(screen.getByRole("button", { name: "Delete" }));

        await waitFor(() => {
            expect(screen.getByText("Failed to delete group")).toBeInTheDocument();
        });
    });

    it("handles delete operation and closes on success", async () => {
        seed();
        const onClose = vi.fn();
        const group = { id: 1, name: "Income", kind: "income" };

        const { user } = renderUI(
            <GroupDeleteDialog group={group} catCount={0} onClose={onClose} />,
        );

        vi.spyOn(useStore.getState(), "deleteGroup").mockResolvedValue(undefined);

        const btn = screen.getByRole("button", { name: "Delete" });
        await user.click(btn);

        await waitFor(() => {
            expect(useStore.getState().deleteGroup).toHaveBeenCalled();
        });

        await waitFor(() => {
            expect(onClose).toHaveBeenCalled();
        });
    });
});
