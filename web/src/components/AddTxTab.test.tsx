import { beforeEach, describe, expect, it, vi } from "vitest";
import AddTxTab from "./AddTxTab.jsx";
import { atDemo, renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import type { UserEvent } from "@testing-library/user-event";
import type { Transaction, TransactionCreate } from "../types.js";

const created = (id: number, body: TransactionCreate): Transaction => ({
    id,
    bankCategory: "",
    transferId: null,
    comment: body.comment ?? "",
    description: body.description ?? "",
    categoryId: body.categoryId ?? null,
    ...body,
});

describe("AddTxTab", () => {
    beforeEach(() => {
        resetStore();
        seed();
    });

    const fillAmount = async (user: UserEvent, amount = "12.50") => {
        await user.type(screen.getByLabelText("Amount"), amount);
    };

    it("renders the fields, preselects the first account, and disables an empty form", () => {
        renderUI(<AddTxTab onClose={vi.fn()} />);
        expect(screen.getByLabelText("Amount")).toBeInTheDocument();
        expect(screen.getByLabelText("Description")).toBeInTheDocument();
        expect(screen.getByLabelText("Date")).toBeInTheDocument();
        expect(screen.getByLabelText("Comment")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Account.*Card/ })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    });

    it("keeps Add disabled for zero, empty, and invalid amounts", async () => {
        const { user } = renderUI(<AddTxTab onClose={vi.fn()} />);
        const add = screen.getByRole("button", { name: "Add" });
        expect(add).toBeDisabled();
        await fillAmount(user, "0");
        expect(add).toBeDisabled();
        await user.clear(screen.getByLabelText("Amount"));
        await fillAmount(user, "oops");
        expect(add).toBeDisabled();
        await user.clear(screen.getByLabelText("Amount"));
        await fillAmount(user, "10");
        expect(add).not.toBeDisabled();
    });

    it("posts an expense and echoes it back, clearing amount but keeping date and account", async () => {
        const add = vi
            .spyOn(useStore.getState(), "addTransaction")
            .mockImplementation(async (body) => created(99, body));
        const { user } = renderUI(<AddTxTab onClose={vi.fn()} />);
        await fillAmount(user, "12.50");
        await user.type(screen.getByLabelText("Description"), "Coffee");
        await user.type(screen.getByLabelText("Comment"), "  latte  ");
        await user.click(screen.getByRole("button", { name: "Add" }));
        await waitFor(() =>
            expect(add).toHaveBeenCalledWith({
                date: add.mock.calls[0]![0].date,
                amount: -1250,
                accountId: 1,
                description: "Coffee",
                categoryId: null,
                comment: "latte",
            }),
        );
        expect(add.mock.calls[0]![0].date).toMatch(/^\d{4}-\d{2}-\d{2}T12:00:00$/);
        expect(await screen.findByText("Added in this session")).toBeInTheDocument();
        expect(screen.getByText("Coffee")).toBeInTheDocument();
        expect(screen.getByLabelText("Amount")).toHaveValue("");
    });

    it("posts an income as a positive amount when the direction is switched", async () => {
        const add = vi
            .spyOn(useStore.getState(), "addTransaction")
            .mockImplementation(async (body) => created(1, body));
        const { user } = renderUI(<AddTxTab onClose={vi.fn()} />);
        await user.click(screen.getByText("Income"));
        await fillAmount(user, "100");
        await user.click(screen.getByRole("button", { name: "Add" }));
        await waitFor(() =>
            expect(add).toHaveBeenCalledWith(expect.objectContaining({ amount: 10000 })),
        );
    });

    it("submits the chosen category and account", async () => {
        const add = vi
            .spyOn(useStore.getState(), "addTransaction")
            .mockImplementation(async (body) => created(5, body));
        const { user } = renderUI(<AddTxTab onClose={vi.fn()} />);
        await fillAmount(user, "30");
        await user.click(screen.getByRole("button", { name: /Category/ }));
        await user.click(await screen.findByRole("option", { name: "Groceries", hidden: true }));
        await user.click(screen.getByRole("button", { name: "Add" }));
        await waitFor(() =>
            expect(add).toHaveBeenCalledWith(expect.objectContaining({ categoryId: 2 })),
        );
    });

    it("clears a chosen category when the direction flips", async () => {
        const { user } = renderUI(<AddTxTab onClose={vi.fn()} />);
        await user.click(screen.getByRole("button", { name: /Category/ }));
        await user.click(await screen.findByRole("option", { name: "Groceries", hidden: true }));
        expect(screen.getByRole("button", { name: /Category.*Groceries/ })).toBeInTheDocument();
        await user.click(screen.getByText("Income"));
        expect(
            screen.queryByRole("button", { name: /Category.*Groceries/ }),
        ).not.toBeInTheDocument();
    });

    it("adds the row on Enter without clicking Add", async () => {
        const add = vi
            .spyOn(useStore.getState(), "addTransaction")
            .mockImplementation(async (body) => created(7, body));
        const { user } = renderUI(<AddTxTab onClose={vi.fn()} />);
        await user.type(screen.getByLabelText("Amount"), "5{Enter}");
        await waitFor(() => expect(add).toHaveBeenCalledOnce());
    });

    it("does nothing on Enter while the form is invalid", async () => {
        const add = vi.spyOn(useStore.getState(), "addTransaction");
        const { user } = renderUI(<AddTxTab onClose={vi.fn()} />);
        await user.type(screen.getByLabelText("Description"), "no amount{Enter}");
        expect(add).not.toHaveBeenCalled();
    });

    it("notifies and keeps the form filled when the store rejects", async () => {
        vi.spyOn(useStore.getState(), "addTransaction").mockRejectedValue(new Error("offline"));
        const notify = vi.spyOn(useStore.getState(), "notify");
        const { user } = renderUI(<AddTxTab onClose={vi.fn()} />);
        await fillAmount(user, "12");
        await user.click(screen.getByRole("button", { name: "Add" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({
                    title: "Failed to add the transaction",
                    theme: "danger",
                }),
            ),
        );
        expect(screen.queryByText("Added in this session")).not.toBeInTheDocument();
    });

    it("warns and stays disabled when there is no account to book against", () => {
        seed({ accounts: [] });
        renderUI(<AddTxTab onClose={vi.fn()} />);
        expect(screen.getByText(/Create an account first/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    });

    it("selects a newly arrived account once the snapshot loads", async () => {
        seed({ accounts: [] });
        renderUI(<AddTxTab onClose={vi.fn()} />);
        expect(screen.queryByRole("button", { name: /Account.*Card/ })).not.toBeInTheDocument();
        seed();
        expect(await screen.findByRole("button", { name: /Account.*Card/ })).toBeInTheDocument();
    });

    it("closes the tab from the header", async () => {
        const close = vi.fn();
        const { user } = renderUI(<AddTxTab onClose={close} />);
        await user.click(screen.getByRole("button", { name: "Close Add transaction" }));
        expect(close).toHaveBeenCalledOnce();
    });

    it("adds a real row to the store snapshot on /demo without touching the network", async () => {
        atDemo();
        const before = useStore.getState().snapshot!.transactions.length;
        const { user } = renderUI(<AddTxTab onClose={vi.fn()} />);
        await user.type(screen.getByLabelText("Amount"), "42");
        await user.type(screen.getByLabelText("Description"), "Demo spend");
        await user.click(screen.getByRole("button", { name: "Add" }));
        await waitFor(() =>
            expect(useStore.getState().snapshot!.transactions.length).toBe(before + 1),
        );
        expect(await screen.findByText("Demo spend")).toBeInTheDocument();
    });
});
