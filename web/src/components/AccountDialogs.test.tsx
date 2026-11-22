import { act } from "@testing-library/react";
import type { ReconcileEvent } from "../types.js";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderUI, resetStore, screen, seed, setPath, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import { AccountDeleteDialog, AccountEditTab, AccountReconcileTab } from "./AccountDialogs.jsx";

const account = {
    id: 1,
    name: "Card",
    type: "card",
    icon: "card",
    color: "#5b6472",
    iconImage: null,
    currency: "RUB",
    sort: 0,
    archived: false,
    openingBalance: 10000,
    openingDate: null,
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
                accounts={useStore.getState().snapshot!.accounts}
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
        vi.spyOn(useStore.getState(), "reconcileHistory")
            .mockResolvedValueOnce([])
            .mockResolvedValue([
                {
                    id: 1,
                    createdAt: "2026-03-01T00:00:00Z",
                    actualBalance: 10250,
                    computedBalance: 10000,
                    delta: 250,
                    adjustmentTxId: null,
                },
            ]);
        const reconcile = vi
            .spyOn(useStore.getState(), "reconcileAccount")
            .mockResolvedValue({ delta: 250 });
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { user } = renderUI(
            <AccountReconcileTab account={account} balance={10000} onClose={close} />,
        );
        expect(screen.getByText(/Computed balance/)).toBeInTheDocument();
        expect(screen.getByText(/No adjustment needed/)).toBeVisible();
        await user.clear(screen.getByLabelText("Actual bank balance"));

        await user.type(screen.getByLabelText("Actual bank balance"), "102.50");
        expect(screen.getByText(/will be posted/)).toBeVisible();
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        await waitFor(() => expect(reconcile).toHaveBeenCalledWith(1, 10250));
        expect(notify).toHaveBeenCalledWith(expect.objectContaining({ theme: "success" }));
        expect(await screen.findByText("Adjusted")).toBeVisible();
        expect(close).not.toHaveBeenCalled();
    });

    it("tracks live balances except while editing, then resets the draft after saving", async () => {
        seed({ accounts: [account] });
        const fetchHistory = vi
            .spyOn(useStore.getState(), "reconcileHistory")
            .mockResolvedValue([]);
        const save = vi
            .spyOn(useStore.getState(), "reconcileAccount")
            .mockResolvedValue({ delta: 0 });
        const tab = (balance: number) => (
            <AccountReconcileTab account={account} balance={balance} onClose={vi.fn()} />
        );
        const { user, rerender } = renderUI(tab(10000));
        const field = screen.getByLabelText<HTMLInputElement>("Actual bank balance");
        rerender(tab(12000));
        expect(Number(field.value)).toBe(120);
        await user.clear(field);
        await user.type(field, "99");
        rerender(tab(13000));
        expect(Number(field.value)).toBe(99);
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        expect(save).toHaveBeenCalledWith(1, 9900);
        rerender(tab(9900));
        rerender(tab(14000));
        expect(Number(field.value)).toBe(140);
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        expect(save).toHaveBeenLastCalledWith(1, 14000);
        await waitFor(() => expect(fetchHistory).toHaveBeenCalledTimes(3));
    });

    it("does not carry a typed balance to another account", async () => {
        seed({ accounts: [account] });
        const save = vi
            .spyOn(useStore.getState(), "reconcileAccount")
            .mockResolvedValue({ delta: 0 });
        vi.spyOn(useStore.getState(), "reconcileHistory").mockResolvedValue([]);
        const view = renderUI(
            <AccountReconcileTab account={account} balance={5000} onClose={vi.fn()} />,
        );
        await view.user.clear(screen.getByLabelText("Actual bank balance"));
        await view.user.type(screen.getByLabelText("Actual bank balance"), "123");
        view.rerender(
            <AccountReconcileTab
                account={{ ...account, id: 2 }}
                balance={2200}
                onClose={vi.fn()}
            />,
        );
        await view.user.click(screen.getByRole("button", { name: "Reconcile" }));
        expect(save).toHaveBeenCalledWith(2, 2200);
    });

    it("keeps the open demo receipt but removes its deleted adjustment link", async () => {
        setPath("/demo/accounts");
        try {
            seed({ accounts: [account] });
            const store = useStore.getState();
            await store.reconcileAccount(1, 12345);
            const [receipt] = await store.reconcileHistory(1);
            renderUI(
                <MemoryRouter>
                    <AccountReconcileTab account={account} balance={12345} onClose={vi.fn()} />
                </MemoryRouter>,
            );
            expect(await screen.findByRole("link")).toBeVisible();
            await act(async () => {
                await store.deleteTransaction(receipt!.adjustmentTxId!);
            });
            await waitFor(() => expect(screen.queryByRole("link")).not.toBeInTheDocument());
            expect(await screen.findByText("Adjusted")).toBeVisible();
        } finally {
            setPath("/");
        }
    });

    it.each(["success", "failure"])(
        "ignores a late %s after switching accounts",
        async (outcome) => {
            let settle!: (rows: ReconcileEvent[]) => void;
            let stale!: (error: Error) => void;
            const first = new Promise<ReconcileEvent[]>((resolve, reject) => {
                settle = resolve;
                stale = reject;
            });
            let offline!: (error: Error) => void;
            const second = new Promise<ReconcileEvent[]>((_resolve, reject) => {
                offline = reject;
            });
            vi.spyOn(useStore.getState(), "reconcileHistory")
                .mockResolvedValueOnce([])
                .mockReturnValueOnce(first)
                .mockReturnValueOnce(second);
            const dialog = (id: number) => (
                <AccountReconcileTab account={{ ...account, id }} balance={0} onClose={vi.fn()} />
            );
            const view = renderUI(dialog(1));
            expect(await screen.findByText("No reconciliations recorded.")).toBeInTheDocument();
            view.rerender(dialog(2));
            expect(screen.getByText("Loading reconciliation history…")).toBeInTheDocument();
            view.rerender(dialog(3));
            await act(async () => {
                if (outcome === "success") settle([]);
                else stale(new Error("stale"));
                await Promise.resolve();
            });
            expect(screen.getByText("Loading reconciliation history…")).toBeInTheDocument();
            offline(new Error("offline"));
            expect(
                await screen.findByText("Could not load reconciliation history."),
            ).toBeInTheDocument();
        },
    );

    it.each(["", "/demo"])("displays receipts and adjustment links under %s", async (prefix) => {
        setPath(`${prefix}/accounts`);
        seed({ accounts: [account] });
        const event = {
            id: 2,
            createdAt: "2026-03-04T12:00:00Z",
            computedBalance: 9000,
            actualBalance: 9000,
            delta: 0,
            adjustmentTxId: null,
        };
        vi.spyOn(useStore.getState(), "reconcileHistory").mockResolvedValue([
            event,
            { ...event, id: 1, computedBalance: 7490, delta: 1510, adjustmentTxId: 42 },
        ]);
        const { user } = renderUI(
            <MemoryRouter>
                <AccountReconcileTab account={account} balance={9000} onClose={vi.fn()} />
            </MemoryRouter>,
        );
        await user.click(await screen.findByText(/Last reconciled:/));
        const stamp = new Intl.DateTimeFormat(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
        }).format(new Date(event.createdAt));
        expect(screen.getByText(/Last reconciled:/)).toHaveTextContent(stamp);
        expect(screen.getByText("Matched")).toHaveAttribute("data-match", "true");
        expect(screen.getByText("Adjusted")).toHaveAttribute("data-match", "false");
        const differences = screen
            .getAllByText("Difference")
            .map((label) => label.nextElementSibling?.textContent);
        const rub = (value: number, digits: number) =>
            new Intl.NumberFormat(undefined, {
                style: "currency",
                currency: "RUB",
                minimumFractionDigits: digits,
            }).format(value);
        expect(differences).toEqual([rub(0, 0), `+${rub(15.1, 2)}`]);
        expect(screen.getAllByRole("listitem")).toHaveLength(2);
        expect(screen.getAllByRole("link")).toHaveLength(1);
        expect(screen.getByRole("link", { name: "Adjustment #42" })).toHaveAttribute(
            "href",
            `${prefix}/transactions?transactionId=42`,
        );
        setPath("/");
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
            <AccountReconcileTab account={account} balance={10000} onClose={vi.fn()} />,
        );
        await user.clear(screen.getByLabelText("Actual bank balance"));
        await user.type(screen.getByLabelText("Actual bank balance"), "-");
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        expect(screen.queryByText(/No adjustment needed|will be posted/)).not.toBeInTheDocument();
        expect(reconcile).not.toHaveBeenCalled();
        expect(screen.getByRole("button", { name: "Reconcile" })).toBeDisabled();
        reconcile.mockResolvedValue({ delta: 0 });
        await user.clear(screen.getByLabelText("Actual bank balance"));
        await user.type(screen.getByLabelText("Actual bank balance"), "100");
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith({ title: "Already reconciled", theme: "success" }),
        );
        rerender(<AccountReconcileTab account={account} balance={10000} onClose={vi.fn()} />);
        reconcile.mockRejectedValue(new Error("offline"));
        await user.click(screen.getByRole("button", { name: "Reconcile" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Failed to reconcile", theme: "danger" }),
            ),
        );
    });
});
