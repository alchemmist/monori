import { beforeEach, describe, expect, it, vi } from "vitest";
import SplitTransactionDialog from "./SplitTransactionDialog.jsx";
import { fireEvent, renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";

const expense = (patch = {}) => ({
    id: 42,
    amount: -1_000,
    description: "Market",
    splits: [],
    ...patch,
});

describe("SplitTransactionDialog", () => {
    beforeEach(() => {
        resetStore();
        seed();
    });

    const renderDialog = (transaction = expense(), onClose = vi.fn()) => ({
        onClose,
        ...renderUI(<SplitTransactionDialog transaction={transaction} onClose={onClose} />),
    });

    const chooseCategories = async (user) => {
        await user.click(screen.getAllByRole("button", { name: "Category" })[0]);
        await user.click(screen.getByRole("option", { name: "Groceries" }));
        await user.click(screen.getAllByRole("button", { name: "Category" })[0]);
        await user.click(screen.getByRole("option", { name: "Rent" }));
    };

    it("keeps the allocation bar visible and balances manual amount entry", async () => {
        const { user } = renderDialog();
        const first = screen.getByLabelText("Part 1 amount");
        const second = screen.getByLabelText("Part 2 amount");
        expect(first).toHaveValue("5");
        expect(second).toHaveValue("5");
        expect(screen.getByLabelText("Boundary between parts 1 and 2")).toBeInTheDocument();

        await user.clear(first);
        expect(screen.getByLabelText("Boundary between parts 1 and 2")).toBeInTheDocument();
        await user.type(first, "6");
        expect(first).toHaveValue("6");
        expect(second).toHaveValue("4");
        expect(screen.getByText("Fully assigned")).toBeInTheDocument();
    });

    it("updates numeric fields from the bar and manages extra parts", async () => {
        const { user } = renderDialog();
        fireEvent.change(screen.getByLabelText("Boundary between parts 1 and 2"), {
            target: { value: "700" },
        });
        expect(screen.getByLabelText("Part 1 amount")).toHaveValue("7");
        expect(screen.getByLabelText("Part 2 amount")).toHaveValue("3");

        await user.click(screen.getByRole("button", { name: "Add part" }));
        expect(screen.getByLabelText("Part 3 amount")).toHaveValue("3,34");
        expect(screen.getAllByRole("slider")).toHaveLength(2);
        await user.click(screen.getByLabelText("Remove part 2"));
        expect(screen.queryByLabelText("Part 3 amount")).not.toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Split evenly" }));
        expect(screen.getByLabelText("Part 1 amount")).toHaveValue("5");
    });

    it("saves expense parts with an automatic sign", async () => {
        const replace = vi
            .spyOn(useStore.getState(), "replaceTransactionSplits")
            .mockResolvedValue([]);
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user } = renderDialog(expense(), close);
        await chooseCategories(user);
        await user.type(screen.getByLabelText("Part 1 comment"), " food ");
        await user.click(screen.getByRole("button", { name: "Save split" }));
        await waitFor(() =>
            expect(replace).toHaveBeenCalledWith(42, [
                { categoryId: 2, amount: -500, comment: "food" },
                { categoryId: 3, amount: -500, comment: "" },
            ]),
        );
        expect(notify).toHaveBeenCalledWith({ title: "Transaction split", theme: "success" });
        expect(close).toHaveBeenCalledOnce();
    });

    it("loads and removes an existing split", async () => {
        const replace = vi
            .spyOn(useStore.getState(), "replaceTransactionSplits")
            .mockResolvedValue([]);
        const close = vi.fn();
        const transaction = expense({
            splits: [
                { id: 1, categoryId: 2, amount: -300, comment: "one" },
                { id: 2, categoryId: 3, amount: -700, comment: "two" },
            ],
        });
        const { user } = renderDialog(transaction, close);
        expect(screen.getByLabelText("Part 1 amount")).toHaveValue("3");
        await user.click(screen.getByRole("button", { name: "Remove split" }));
        await waitFor(() => expect(replace).toHaveBeenCalledWith(42, []));
        expect(close).toHaveBeenCalledOnce();
    });

    it("reports save and removal failures", async () => {
        vi.spyOn(useStore.getState(), "replaceTransactionSplits").mockRejectedValue(
            new Error("offline"),
        );
        const notify = vi.spyOn(useStore.getState(), "notify");
        const transaction = expense({
            splits: [
                { id: 1, categoryId: 2, amount: -500, comment: "" },
                { id: 2, categoryId: 3, amount: -500, comment: "" },
            ],
        });
        const { user } = renderDialog(transaction);
        await user.click(screen.getByRole("button", { name: "Save split" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Failed to split transaction" }),
            ),
        );
        await user.click(screen.getByRole("button", { name: "Remove split" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Failed to remove split" }),
            ),
        );
    });

    it("renders nothing without a transaction", () => {
        renderDialog(null);
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("does not render allocation controls for an amount too small to split", () => {
        renderDialog(expense({ amount: 0 }));
        expect(
            screen.getByText("This transaction amount is too small to split."),
        ).toBeInTheDocument();
        expect(screen.queryByRole("slider")).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Save split" })).not.toBeInTheDocument();
    });
});
