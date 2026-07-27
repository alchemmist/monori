import { beforeEach, describe, expect, it, vi } from "vitest";
import DeleteTxDialog from "./DeleteTxDialog.jsx";
import { renderUI, resetStore, screen, seed, tx, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";

describe("DeleteTxDialog", () => {
    beforeEach(() => {
        resetStore();
        seed();
    });

    const renderDialog = (props = {}) => {
        const row = props.tx ?? tx(1, { description: "Coffee", amount: -25000 });
        return {
            ...renderUI(<DeleteTxDialog tx={row} onClose={vi.fn()} {...props} />),
            row,
        };
    };

    it("spells out the row it is about to delete", () => {
        renderDialog();
        expect(screen.getByText(/Coffee/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Hide it instead" })).toBeInTheDocument();
    });

    it("falls back to a placeholder when the row has no description", () => {
        renderDialog({ tx: tx(2, { description: "" }) });
        expect(screen.getByText(/no description/)).toBeInTheDocument();
    });

    it("deletes, notifies, and closes on success", async () => {
        const del = vi.spyOn(useStore.getState(), "deleteTransaction").mockResolvedValue(true);
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user, row } = renderDialog({ onClose: close });
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(del).toHaveBeenCalledWith(row.id));
        expect(notify).toHaveBeenCalledWith({ title: "Transaction deleted", theme: "success" });
        expect(close).toHaveBeenCalledOnce();
    });

    it("does not close when the delete reports nothing was removed", async () => {
        vi.spyOn(useStore.getState(), "deleteTransaction").mockResolvedValue(false);
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user } = renderDialog({ onClose: close });
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(close).not.toHaveBeenCalled());
        expect(notify).not.toHaveBeenCalled();
    });

    it("reports a failure through a danger toast and keeps the dialog open", async () => {
        const error = new Error("offline");
        vi.spyOn(useStore.getState(), "deleteTransaction").mockRejectedValue(error);
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user } = renderDialog({ onClose: close });
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith({
                title: "Failed to delete transaction",
                theme: "danger",
                content: "Error: offline",
            }),
        );
        expect(close).not.toHaveBeenCalled();
    });

    it("hides the row and closes when asked to hide instead", async () => {
        const hide = vi.spyOn(useStore.getState(), "hideTx").mockImplementation(() => {});
        const close = vi.fn();
        const { user, row } = renderDialog({ onClose: close });
        await user.click(screen.getByRole("button", { name: "Hide it instead" }));
        expect(hide).toHaveBeenCalledWith(row.id);
        expect(close).toHaveBeenCalledOnce();
    });
});
