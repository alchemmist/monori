import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useStore } from "./store.js";

const snapshot = () => ({
    accounts: [{ id: 1, name: "Card", openingBalance: 100, archived: false }],
    groups: [{ id: 1, name: "Income", kind: "income", sort: 1 }, { id: 2, name: "Home", kind: "expense", sort: 2 }],
    categories: [{ id: 1, groupId: 1, name: "Salary", sort: 1 }, { id: 2, groupId: 2, name: "Food", keywords: "shop", sort: 2 }],
    budgets: [{ categoryId: 2, year: 2026, month: 1, amount: 20 }],
    transactions: [{ id: 1, date: "2026-01-01", amount: 50, accountId: 1, categoryId: 1 }],
    connections: [],
});

beforeEach(() => {
    window.history.replaceState({}, "", "/demo");
    useStore.setState({ snapshot: snapshot(), toast: null, tabs: [], loading: false });
});
afterEach(() => { window.history.replaceState({}, "", "/"); vi.restoreAllMocks(); });

describe("store demo mutations", () => {
    it("edits budgets and transaction category/account optimistically", () => {
        const store = useStore.getState();
        store.setBudget(2, 2026, 1, 30); store.setBudget(2, 2026, 2, 10);
        store.setTxCategory(1, null); store.setTxAccount(1, 9);
        expect(useStore.getState().snapshot.budgets).toEqual(expect.arrayContaining([{ categoryId: 2, year: 2026, month: 1, amount: 30 }, { categoryId: 2, year: 2026, month: 2, amount: 10 }]));
        expect(useStore.getState().snapshot.transactions[0]).toMatchObject({ categoryId: null, accountId: 9 });
    });

    it("creates, patches, removes and reconciles accounts", async () => {
        const store = useStore.getState();
        const id = await store.createAccount({ name: "Cash", openingBalance: 20 });
        await store.patchAccount(id, { archived: true });
        await store.deleteAccount(id);
        const result = await store.reconcileAccount(1, 200);
        expect(result.delta).toBe(50);
        expect(useStore.getState().snapshot.accounts).toHaveLength(1);
        expect(useStore.getState().snapshot.transactions.at(-1)).toMatchObject({ amount: 50, source: "adjustment" });
    });

    it("creates and deletes both legs of a transfer", async () => {
        const store = useStore.getState();
        const transferId = await store.createTransfer({ fromAccountId: 1, toAccountId: 2, amount: 25, date: "2026-01-02", comment: "move" });
        expect(useStore.getState().snapshot.transactions.filter((t) => t.transferId === transferId)).toHaveLength(2);
        await store.deleteTransfer(transferId);
        expect(useStore.getState().snapshot.transactions).toHaveLength(1);
    });

    it("manages categories and groups locally including a merge and reorder", async () => {
        const store = useStore.getState();
        const category = await store.createCategory({ name: "Rent", groupId: 2 });
        await store.patchCategory(category, { keywords: "home" });
        await store.moveCategory(category, 2, [category, 2, 1]);
        await store.mergeCategory(category, 2);
        const group = await store.createGroup({ name: "Fun", kind: "expense" });
        await store.patchGroup(group, { name: "Joy" });
        await store.reorderGroups([group, 2, 1]);
        await store.deleteGroup(group);
        expect(useStore.getState().snapshot.categories.map((c) => c.id)).not.toContain(category);
        expect(useStore.getState().snapshot.groups.map((g) => g.id)).not.toContain(group);
    });

    it("keeps imports inert and rejects unavailable bank sync in the demo", async () => {
        const store = useStore.getState();
        await expect(store.commitImport([], 1)).resolves.toMatchObject({ demo: true });
        await expect(store.createConnection({})).rejects.toThrow(/not available/i);
        await expect(store.syncConnection(1)).rejects.toThrow(/not available/i);
        await expect(store.submitConnectionSms(1, "1234")).rejects.toThrow(/not available/i);
        await expect(store.deleteConnection(1)).resolves.toBeUndefined();
        await expect(store.cancelConnectionSync(1)).resolves.toBeUndefined();
    });
});
