import { beforeEach, describe, expect, it, vi } from "vitest";
import TransferDialog from "./TransferDialog.jsx";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import { api } from "../api.js";
import { buildSnapshot } from "../test/render.js";
import type { ComponentProps } from "react";
import type { UserEvent } from "@testing-library/user-event";

const accounts = buildSnapshot({
    accounts: [
        { id: 1, name: "Card", archived: false },
        { id: 2, name: "Cash", archived: false },
        { id: 3, name: "Old card", archived: true },
    ],
}).accounts;

describe("TransferDialog", () => {
    beforeEach(() => {
        resetStore();
        seed({ accounts });
    });

    const renderDialog = (props: Partial<ComponentProps<typeof TransferDialog>> = {}) =>
        renderUI(<TransferDialog accounts={accounts} onClose={vi.fn()} {...props} />);
    const fillAmount = async (user: UserEvent, amount = "12.50") => {
        await user.type(screen.getByLabelText("Amount"), amount);
    };

    it("offers only active accounts and disables an incomplete transfer", () => {
        renderDialog();
        expect(screen.getByRole("button", { name: /from.*card/i })).toBeInTheDocument();
        expect(screen.queryByText("Old card")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
    });

    it("submits normalized values and closes after a successful transfer", async () => {
        const create = vi.spyOn(useStore.getState(), "createTransfer").mockResolvedValue("t1");
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user } = renderDialog({ onClose: close });
        await fillAmount(user);
        await user.type(screen.getByLabelText("Comment"), "  ATM  ");
        await user.click(screen.getByRole("button", { name: "Transfer" }));
        await waitFor(() =>
            expect(create).toHaveBeenCalledWith({
                fromAccountId: 1,
                toAccountId: 2,
                amount: 1250,
                date: create.mock.calls[0]![0].date,
                comment: "ATM",
            }),
        );
        expect(create.mock.calls[0]![0].date).toMatch(/^\d{4}-\d{2}-\d{2}T12:00:00$/);
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
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith({
                title: "Failed to create transfer",
                theme: "danger",
                content: "Error: offline",
            }),
        );
        expect(close).not.toHaveBeenCalled();
    });

    it("handles the empty and one-account states without allowing a transfer", () => {
        const { unmount } = renderUI(<TransferDialog accounts={[]} onClose={vi.fn()} />);
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
        unmount();
        renderUI(<TransferDialog accounts={[accounts[0]!]} onClose={vi.fn()} />);
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
    });

    it("uses the selected day's rate for a cross-currency transfer", async () => {
        const mixed = buildSnapshot({
            accounts: [
                { id: 1, name: "Rubles", currency: "RUB", archived: false },
                { id: 2, name: "Dollars", currency: "USD", archived: false },
            ],
        }).accounts;
        vi.spyOn(api, "rates").mockResolvedValue({ rates: [{ code: "USD", rate: 90 }] });
        const create = vi.spyOn(useStore.getState(), "createTransfer").mockResolvedValue("t1");
        const { user } = renderUI(<TransferDialog accounts={mixed} onClose={vi.fn()} />);
        await user.type(screen.getByLabelText("Sent (RUB)"), "900");
        expect(screen.getByLabelText("Received (USD)")).toHaveAttribute("placeholder", "10");
        await user.click(screen.getByRole("button", { name: "Transfer" }));
        await waitFor(() =>
            expect(create).toHaveBeenCalledWith(
                expect.objectContaining({ amount: 90_000, toAmount: 1_000 }),
            ),
        );
    });

    it("accepts an explicit received amount when a dated rate is unavailable", async () => {
        const mixed = buildSnapshot({
            accounts: [
                { id: 1, name: "Rubles", currency: "RUB", archived: false },
                { id: 2, name: "Dollars", currency: "USD", archived: false },
            ],
        }).accounts;
        vi.spyOn(api, "rates").mockResolvedValue({ rates: [] });
        const create = vi.spyOn(useStore.getState(), "createTransfer").mockResolvedValue("t1");
        const { user } = renderUI(<TransferDialog accounts={mixed} onClose={vi.fn()} />);
        await user.type(screen.getByLabelText("Sent (RUB)"), "90");
        expect(
            await screen.findByText(/No exchange rate is available for this date/),
        ).toBeInTheDocument();
        await user.type(screen.getByLabelText("Received (USD)"), "1.25");
        await user.click(screen.getByRole("button", { name: "Transfer" }));
        await waitFor(() =>
            expect(create).toHaveBeenCalledWith(expect.objectContaining({ toAmount: 125 })),
        );
    });
});
