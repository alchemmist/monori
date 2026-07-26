import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import { AccountDeleteDialog, AccountEditTab, AccountReconcileDialog } from "./AccountDialogs.jsx";

const account = {
    id: 1,
    name: "Card",
    type: "card",
    icon: "card",
    color: "#5b6472",
    currency: "RUB",
    openingBalance: 10000,
    cardTails: ["8181"],
};

describe("account dialogs", () => {
    beforeEach(resetStore);

    it("creates an account with its edited form fields", async () => {
        seed({
            accounts: [
                account,
                { ...account, id: 2, name: "Saved", iconImage: "data:image/png,x" },
            ],
        });
        const create = vi.spyOn(useStore.getState(), "createAccount").mockResolvedValue(3);
        const close = vi.fn();
        const { user } = renderUI(<AccountEditTab account={{}} onClose={close} />);
        await user.type(screen.getByLabelText("Name"), "Cash");
        await user.clear(screen.getByLabelText("Opening balance"));
        await user.type(screen.getByLabelText("Opening balance"), "12.50");
        await user.type(screen.getByLabelText("Card tails"), " 1234, xx56 ");
        await user.click(screen.getByRole("button", { name: "Create" }));
        await waitFor(() =>
            expect(create).toHaveBeenCalledWith(
                expect.objectContaining({
                    name: "Cash",
                    openingBalance: 1250,
                    cardTails: ["1234", "56"],
                }),
            ),
        );
        expect(close).toHaveBeenCalled();
    });

    it("rejects an invalid opening balance before saving", async () => {
        seed({ accounts: [account] });
        const notify = vi.spyOn(useStore.getState(), "notify");
        const { user } = renderUI(<AccountEditTab account={account} onClose={vi.fn()} />);
        await user.clear(screen.getByLabelText("Opening balance"));
        await user.type(screen.getByLabelText("Opening balance"), "-");
        await user.click(screen.getByRole("button", { name: "Save" }));
        expect(notify).toHaveBeenCalledWith(
            expect.objectContaining({ title: "Opening balance is not a number" }),
        );
    });

    it("requires a reassignment for an account with transactions", async () => {
        seed({ accounts: [account, { ...account, id: 2, name: "Cash" }] });
        const remove = vi.spyOn(useStore.getState(), "deleteAccount").mockResolvedValue();
        const { user } = renderUI(
            <AccountDeleteDialog
                account={account}
                accounts={useStore.getState().snapshot.accounts}
                txCount={2}
                onClose={vi.fn()}
            />,
        );
        expect(screen.getByText(/2 transactions belong/)).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(remove).toHaveBeenCalledWith(1, 2));
    });

    it("posts a reconciliation adjustment and validates bad balances", async () => {
        seed({ accounts: [account] });
        const reconcile = vi
            .spyOn(useStore.getState(), "reconcileAccount")
            .mockResolvedValue({ delta: 250 });
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user } = renderUI(
            <AccountReconcileDialog account={account} balance={10000} onClose={close} />,
        );
        expect(screen.getByText(/Computed balance/)).toBeInTheDocument();
        await user.clear(screen.getByLabelText("Actual bank balance"));
        await user.type(screen.getByLabelText("Actual bank balance"), "102.50");
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        await waitFor(() => expect(reconcile).toHaveBeenCalledWith(1, 10250));
        expect(notify).toHaveBeenCalledWith(expect.objectContaining({ theme: "success" }));
        expect(close).toHaveBeenCalled();
    });

    it("updates an existing account and reports a failed save", async () => {
        seed({ accounts: [account] });
        const patch = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        const close = vi.fn();
        const { user } = renderUI(<AccountEditTab account={account} onClose={close} />);
        await user.clear(screen.getByLabelText("Name"));
        await user.type(screen.getByLabelText("Name"), "Main card");
        await user.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() =>
            expect(patch).toHaveBeenCalledWith(
                1,
                expect.objectContaining({ name: "Main card", currency: "RUB" }),
            ),
        );
        expect(close).toHaveBeenCalledOnce();
    });

    it("does not save a blank name and reports create failures", async () => {
        seed({ accounts: [account] });
        const create = vi
            .spyOn(useStore.getState(), "createAccount")
            .mockRejectedValue(new Error("offline"));
        const notify = vi.spyOn(useStore.getState(), "notify");
        const { user } = renderUI(<AccountEditTab account={{}} onClose={vi.fn()} />);
        expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
        await user.type(screen.getByLabelText("Name"), "Cash");
        await user.click(screen.getByRole("button", { name: "Create" }));
        await waitFor(() => expect(create).toHaveBeenCalled());
        expect(notify).toHaveBeenCalledWith(
            expect.objectContaining({ title: "Failed to create account", theme: "danger" }),
        );
    });

    it("reuses a saved account image, removes it again, and saves the selected appearance", async () => {
        const image = "data:image/png,reusable";
        seed({ accounts: [account, { ...account, id: 2, name: "Saved", iconImage: image }] });
        const create = vi.spyOn(useStore.getState(), "createAccount").mockResolvedValue(3);
        const { user } = renderUI(<AccountEditTab account={{}} onClose={vi.fn()} />);

        await user.type(screen.getByLabelText("Name"), "Travel");
        await user.click(screen.getByTitle("Reuse this image"));
        expect(
            screen.getByText("Using a custom image. Icon and color don't apply."),
        ).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Create" }));
        await waitFor(() =>
            expect(create).toHaveBeenCalledWith(expect.objectContaining({ iconImage: image })),
        );

        await user.click(screen.getByTitle("Remove custom image"));
        expect(
            screen.queryByText("Using a custom image. Icon and color don't apply."),
        ).not.toBeInTheDocument();
        await user.click(screen.getByLabelText("wallet"));
        await user.click(screen.getByRole("button", { name: "Create" }));
        await waitFor(() =>
            expect(create).toHaveBeenLastCalledWith(
                expect.objectContaining({ icon: "wallet", iconImage: "" }),
            ),
        );
    });

    it("persists a changed icon, colour, opening date, and cleaned card tails", async () => {
        seed({ accounts: [account] });
        const patch = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        const { user } = renderUI(
            <AccountEditTab
                account={{ ...account, openingDate: "2026-02-03T12:00:00", cardTails: [] }}
                onClose={vi.fn()}
            />,
        );
        await user.click(screen.getByLabelText("heart"));
        await user.click(screen.getByLabelText("#ef4444"));
        await user.clear(screen.getByLabelText("Opening date"));
        await user.type(screen.getByLabelText("Opening date"), "2026-04-05");
        await user.type(screen.getByLabelText("Card tails"), " 1111, card-2222, ");
        await user.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() =>
            expect(patch).toHaveBeenCalledWith(
                1,
                expect.objectContaining({
                    icon: "heart",
                    color: "#ef4444",
                    openingDate: "2026-04-05",
                    cardTails: ["1111", "2222"],
                }),
            ),
        );
    });

    it("deletes an empty account without a target and reports deletion errors", async () => {
        seed({ accounts: [account] });
        const remove = vi.spyOn(useStore.getState(), "deleteAccount").mockResolvedValue();
        const close = vi.fn();
        const { user } = renderUI(
            <AccountDeleteDialog
                account={account}
                accounts={[account]}
                txCount={0}
                onClose={close}
            />,
        );
        expect(screen.getByText("No transactions belong to this account.")).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(remove).toHaveBeenCalledWith(1, undefined));
        expect(close).toHaveBeenCalledOnce();
    });

    it("shows reconciliation validation, zero-delta result, and failure", async () => {
        seed({ accounts: [account] });
        const reconcile = vi.spyOn(useStore.getState(), "reconcileAccount");
        const notify = vi.spyOn(useStore.getState(), "notify");
        const { user, rerender } = renderUI(
            <AccountReconcileDialog account={account} balance={10000} onClose={vi.fn()} />,
        );
        await user.clear(screen.getByLabelText("Actual bank balance"));
        await user.type(screen.getByLabelText("Actual bank balance"), "-");
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        expect(reconcile).not.toHaveBeenCalled();
        expect(notify).toHaveBeenCalledWith({ title: "Balance is not a number", theme: "danger" });
        reconcile.mockResolvedValue({ delta: 0 });
        await user.clear(screen.getByLabelText("Actual bank balance"));
        await user.type(screen.getByLabelText("Actual bank balance"), "100");
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith({ title: "Already reconciled", theme: "success" }),
        );
        rerender(<AccountReconcileDialog account={account} balance={10000} onClose={vi.fn()} />);
        reconcile.mockRejectedValue(new Error("offline"));
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Failed to reconcile", theme: "danger" }),
            ),
        );
    });
});
