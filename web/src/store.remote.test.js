import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { useStore } from "./store.js";

const base = () => ({
    accounts: [{ id: 1, name: "Card", openingBalance: 100, archived: false, sort: 1 }],
    groups: [{ id: 2, name: "Home", kind: "expense", sort: 2 }],
    categories: [{ id: 4, groupId: 2, name: "Food", keywords: "shop", sort: 2, archived: false }],
    budgets: [{ categoryId: 4, year: 2026, month: 1, amount: 20 }],
    transactions: [
        { id: 2, date: "2026-01-01", amount: 50, accountId: 1, categoryId: 4, transferId: null },
    ],
    connections: [],
});

const snap = () => useStore.getState().snapshot;

beforeEach(() => {
    window.history.replaceState({}, "", "/app");
    useStore.setState({ snapshot: base(), toast: null, loading: false });
    useStore.setState({ load: vi.fn().mockResolvedValue() });
});

afterEach(() => {
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
});

describe("optimistic edits outside the demo", () => {
    it("persists a budget cell with its exact coordinates", async () => {
        const put = vi.spyOn(api, "putBudget").mockResolvedValue({});
        useStore.getState().setBudget(4, 2026, 1, 35);
        expect(put).toHaveBeenCalledExactlyOnceWith({
            categoryId: 4,
            year: 2026,
            month: 1,
            amount: 35,
        });
        expect(snap().budgets).toEqual([{ categoryId: 4, year: 2026, month: 1, amount: 35 }]);
    });

    it("warns but keeps the optimistic budget when the save fails", async () => {
        vi.spyOn(api, "putBudget").mockRejectedValue(new Error("offline"));
        useStore.getState().setBudget(4, 2026, 1, 35);
        await vi.waitFor(() => expect(useStore.getState().toast).not.toBeNull());
        expect(useStore.getState().toast).toEqual({
            title: "Failed to save budget",
            theme: "danger",
            content: "Error: offline",
        });
        expect(snap().budgets).toEqual([{ categoryId: 4, year: 2026, month: 1, amount: 35 }]);
    });

    it("sends a category retag and maps an unfiled row to category zero", async () => {
        const patch = vi.spyOn(api, "patchTx").mockResolvedValue({});
        useStore.getState().setTxCategory(2, 9);
        expect(patch).toHaveBeenCalledExactlyOnceWith(2, { categoryId: 9 });

        useStore.getState().setTxCategory(2, null);
        expect(patch).toHaveBeenLastCalledWith(2, { categoryId: 0 });
        expect(snap().transactions[0].categoryId).toBeNull();
    });

    it("warns when a category retag fails to persist", async () => {
        vi.spyOn(api, "patchTx").mockRejectedValue(new Error("offline"));
        useStore.getState().setTxCategory(2, 9);
        await vi.waitFor(() => expect(useStore.getState().toast).not.toBeNull());
        expect(useStore.getState().toast).toEqual({
            title: "Failed to update transaction",
            theme: "danger",
            content: "Error: offline",
        });
    });

    it("sends an account move for the transaction", async () => {
        const patch = vi.spyOn(api, "patchTx").mockResolvedValue({});
        useStore.getState().setTxAccount(2, 5);
        expect(patch).toHaveBeenCalledExactlyOnceWith(2, { accountId: 5 });
        expect(snap().transactions[0].accountId).toBe(5);
    });

    it("warns when an account move fails to persist", async () => {
        vi.spyOn(api, "patchTx").mockRejectedValue(new Error("offline"));
        useStore.getState().setTxAccount(2, 5);
        await vi.waitFor(() => expect(useStore.getState().toast).not.toBeNull());
        expect(useStore.getState().toast).toEqual({
            title: "Failed to move transaction",
            theme: "danger",
            content: "Error: offline",
        });
    });
});

describe("server ids and defaults outside the demo", () => {
    it("keeps the server account id rather than deriving one locally", async () => {
        vi.spyOn(api, "createAccount").mockResolvedValue({ id: 77 });
        const id = await useStore.getState().createAccount({ name: "Cash" });
        expect(id).toBe(77);
        expect(snap().accounts.at(-1)).toMatchObject({ id: 77, name: "Cash", currency: "RUB" });
    });

    it("keeps the server category id rather than deriving one locally", async () => {
        vi.spyOn(api, "createCategory").mockResolvedValue({ id: 88 });
        const id = await useStore.getState().createCategory({ name: "Rent", groupId: 2 });
        expect(id).toBe(88);
        expect(snap().categories.at(-1)).toMatchObject({ id: 88, keywords: "" });
    });

    it("keeps the server group id rather than deriving one locally", async () => {
        vi.spyOn(api, "createGroup").mockResolvedValue({ id: 99 });
        const id = await useStore.getState().createGroup({ name: "Fun", kind: "expense" });
        expect(id).toBe(99);
        expect(snap().groups.at(-1)).toEqual({ id: 99, name: "Fun", kind: "expense", sort: 1e9 });
    });
});

describe("deletes reach the server before the snapshot is trimmed", () => {
    it("deletes a category on the server and unfiles its rows locally", async () => {
        const remove = vi.spyOn(api, "deleteCategory").mockResolvedValue({});
        await useStore.getState().deleteCategory(4);
        expect(remove).toHaveBeenCalledExactlyOnceWith(4);
        expect(snap().categories).toEqual([]);
        expect(snap().budgets).toEqual([]);
        expect(snap().transactions[0].categoryId).toBeNull();
    });

    it("leaves the snapshot untouched when the server refuses the delete", async () => {
        vi.spyOn(api, "deleteCategory").mockRejectedValue(new Error("in use"));
        await expect(useStore.getState().deleteCategory(4)).rejects.toThrow("in use");
        expect(snap().categories).toEqual(base().categories);
        expect(snap().budgets).toEqual(base().budgets);
    });

    it("leaves the accounts untouched when the server refuses the delete", async () => {
        vi.spyOn(api, "deleteAccount").mockRejectedValue(new Error("in use"));
        await expect(useStore.getState().deleteAccount(1, 2)).rejects.toThrow("in use");
        expect(snap().accounts).toEqual(base().accounts);
    });

    it("leaves the groups untouched when the server refuses the delete", async () => {
        vi.spyOn(api, "deleteGroup").mockRejectedValue(new Error("in use"));
        await expect(useStore.getState().deleteGroup(2)).rejects.toThrow("in use");
        expect(snap().groups).toEqual(base().groups);
    });

    it("leaves the transfer legs in place when the server refuses the delete", async () => {
        vi.spyOn(api, "deleteTransfer").mockRejectedValue(new Error("gone"));
        await expect(useStore.getState().deleteTransfer("t-1")).rejects.toThrow("gone");
        expect(snap().transactions).toEqual(base().transactions);
    });
});

describe("moveCategory outside the demo", () => {
    it("skips the group patch when the card stays in its group", async () => {
        const patch = vi.spyOn(api, "patchCategory").mockResolvedValue({});
        const reorder = vi.spyOn(api, "reorderCategories").mockResolvedValue({});
        await useStore.getState().moveCategory(4, 2, [4]);
        expect(patch).not.toHaveBeenCalled();
        expect(reorder).toHaveBeenCalledExactlyOnceWith([4]);
    });

    it("skips the group patch when the dragged id is not in the snapshot", async () => {
        const patch = vi.spyOn(api, "patchCategory").mockResolvedValue({});
        vi.spyOn(api, "reorderCategories").mockResolvedValue({});
        await useStore.getState().moveCategory(404, 1, [4]);
        expect(patch).not.toHaveBeenCalled();
        expect(snap().categories[0].groupId).toBe(2);
    });
});
