import { beforeEach, describe, expect, it, vi } from "vitest";
import TransferDialog from "./TransferDialog.jsx";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";

const accounts = [
    { id: 1, name: "Card", archived: false },
    { id: 2, name: "Cash", archived: false },
    { id: 3, name: "Old card", archived: true },
];

describe("TransferDialog", () => {
    beforeEach(() => {
        resetStore();
        seed({ accounts });
    });

    const renderDialog = (props = {}) => renderUI(<TransferDialog accounts={accounts} onClose={vi.fn()} {...props} />);
    const fillAmount = async (user, amount = "12.50") => {
        await user.type(screen.getByLabelText("Amount"), amount);
    };

    it("offers only active accounts and disables an incomplete transfer", () => {
        renderDialog();
        expect(screen.getByRole("button", { name: /from.*card/i })).toBeInTheDocument();
        expect(screen.queryByText("Old card")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
    });

    it("submits normalized values and closes after a successful transfer", async () => {
        const create = vi.spyOn(useStore.getState(), "createTransfer").mockResolvedValue();
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user } = renderDialog({ onClose: close });
        await fillAmount(user);
        await user.type(screen.getByLabelText("Comment"), "  ATM  ");
        await user.click(screen.getByRole("button", { name: "Transfer" }));
        await waitFor(() => expect(create).toHaveBeenCalledWith({
            fromAccountId: 1, toAccountId: 2, amount: 1250,
            date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T12:00:00$/), comment: "ATM",
        }));
        expect(notify).toHaveBeenCalledWith({ title: "Transfer created", theme: "success" });
        expect(close).toHaveBeenCalledOnce();
    });

    it("keeps the action disabled for zero and invalid amounts", async () => {
        const { user } = renderDialog();
        await fillAmount(user, "0");
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
        await user.clear(screen.getByLabelText("Amount"));
        await fillAmount(user, "oops");
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
    });

    it("prevents choosing the same account and explains why", async () => {
        const { user } = renderDialog();
        await user.click(screen.getByRole("button", { name: /to.*cash/i }));
        await user.click(await screen.findByRole("option", { name: "Card", hidden: true }));
        expect(screen.getByText("Pick two different accounts.")).toBeInTheDocument();
        await fillAmount(user);
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
    });

    it("reports failures and leaves the dialog open", async () => {
        const error = new Error("offline");
        vi.spyOn(useStore.getState(), "createTransfer").mockRejectedValue(error);
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user } = renderDialog({ onClose: close });
        await fillAmount(user);
        await user.click(screen.getByRole("button", { name: "Transfer" }));
        await waitFor(() => expect(notify).toHaveBeenCalledWith({
            title: "Failed to create transfer", theme: "danger", content: "Error: offline",
        }));
        expect(close).not.toHaveBeenCalled();
    });

    it("handles the empty and one-account states without allowing a transfer", () => {
        const { unmount } = renderUI(<TransferDialog accounts={[]} onClose={vi.fn()} />);
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
        unmount();
        renderUI(<TransferDialog accounts={[accounts[0]]} onClose={vi.fn()} />);
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
    });
});
