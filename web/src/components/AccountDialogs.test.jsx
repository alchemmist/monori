import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import { AccountDeleteDialog, AccountEditTab, AccountReconcileDialog } from "./AccountDialogs.jsx";

const account = { id: 1, name: "Card", type: "card", icon: "card", color: "#5b6472", currency: "RUB", openingBalance: 10000, cardTails: ["8181"] };

describe("account dialogs", () => {
    beforeEach(resetStore);

    it("creates an account with its edited form fields", async () => {
        seed({ accounts: [account, { ...account, id: 2, name: "Saved", iconImage: "data:image/png,x" }] });
        const create = vi.spyOn(useStore.getState(), "createAccount").mockResolvedValue(3);
        const close = vi.fn();
        const { user } = renderUI(<AccountEditTab account={{}} onClose={close} />);
        await user.type(screen.getByLabelText("Name"), "Cash");
        await user.clear(screen.getByLabelText("Opening balance")); await user.type(screen.getByLabelText("Opening balance"), "12.50");
        await user.type(screen.getByLabelText("Card tails"), " 1234, xx56 ");
        await user.click(screen.getByRole("button", { name: "Create" }));
        await waitFor(() => expect(create).toHaveBeenCalledWith(expect.objectContaining({ name: "Cash", openingBalance: 1250, cardTails: ["1234", "56"] })));
        expect(close).toHaveBeenCalled();
    });

    it("rejects an invalid opening balance before saving", async () => {
        seed({ accounts: [account] }); const notify = vi.spyOn(useStore.getState(), "notify");
        const { user } = renderUI(<AccountEditTab account={account} onClose={vi.fn()} />);
        await user.clear(screen.getByLabelText("Opening balance")); await user.type(screen.getByLabelText("Opening balance"), "nope");
        await user.click(screen.getByRole("button", { name: "Save" }));
        expect(notify).toHaveBeenCalledWith(expect.objectContaining({ title: "Opening balance is not a number" }));
    });

    it("requires a reassignment for an account with transactions", async () => {
        seed({ accounts: [account, { ...account, id: 2, name: "Cash" }] });
        const remove = vi.spyOn(useStore.getState(), "deleteAccount").mockResolvedValue();
        const { user } = renderUI(<AccountDeleteDialog account={account} accounts={useStore.getState().snapshot.accounts} txCount={2} onClose={vi.fn()} />);
        expect(screen.getByText(/2 transactions belong/)).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(remove).toHaveBeenCalledWith(1, 2));
    });

    it("posts a reconciliation adjustment and validates bad balances", async () => {
        seed({ accounts: [account] });
        const reconcile = vi.spyOn(useStore.getState(), "reconcileAccount").mockResolvedValue({ delta: 250 });
        const notify = vi.spyOn(useStore.getState(), "notify"); const close = vi.fn();
        const { user } = renderUI(<AccountReconcileDialog account={account} balance={10000} onClose={close} />);
        expect(screen.getByText(/Computed balance/)).toBeInTheDocument();
        await user.clear(screen.getByLabelText("Actual bank balance")); await user.type(screen.getByLabelText("Actual bank balance"), "102.50");
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        await waitFor(() => expect(reconcile).toHaveBeenCalledWith(1, 10250));
        expect(notify).toHaveBeenCalledWith(expect.objectContaining({ theme: "success" })); expect(close).toHaveBeenCalled();
    });
});
