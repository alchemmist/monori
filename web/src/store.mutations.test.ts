import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useStore } from "./store.js";
import { api } from "./api.js";
import { buildSnapshot } from "./test/render.js";

const snapshot = () =>
    buildSnapshot({
        accounts: [{ id: 1, name: "Card", openingBalance: 100, archived: false }],
        groups: [
            { id: 1, name: "Income", kind: "income", sort: 1 },
            { id: 2, name: "Home", kind: "expense", sort: 2 },
        ],
        categories: [
            { id: 1, groupId: 1, name: "Salary", sort: 1 },
            { id: 2, groupId: 2, name: "Food", keywords: "shop", sort: 2 },
        ],
        budgets: [{ categoryId: 2, year: 2026, month: 1, amount: 20 }],
        transactions: [{ id: 1, date: "2026-01-01", amount: 50, accountId: 1, categoryId: 1 }],
        connections: [],
    });

beforeEach(() => {
    window.history.replaceState({}, "", "/demo");
    useStore.setState({ snapshot: snapshot(), toast: null, tabs: [], loading: false });
});
afterEach(() => {
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
});

describe("store demo mutations", () => {
    it("edits budgets and transaction category/account optimistically", () => {
        const store = useStore.getState();
        void store.setBudget(2, 2026, 1, 30);
        void store.setBudget(2, 2026, 2, 10);
        store.setTxCategory(1, null);
        store.setTxAccount(1, 9);
        expect(useStore.getState().snapshot!.budgets).toEqual(
            expect.arrayContaining([
                { categoryId: 2, year: 2026, month: 1, amount: 30 },
                { categoryId: 2, year: 2026, month: 2, amount: 10 },
            ]),
        );
        expect(useStore.getState().snapshot!.transactions[0]).toMatchObject({
            categoryId: null,
            accountId: 9,
        });
    });

    it("creates, patches, removes and reconciles accounts", async () => {
        const store = useStore.getState();
        const id = await store.createAccount({ name: "Cash", openingBalance: 20 });
        await store.patchAccount(id, { archived: true });
        await store.deleteAccount(id);
        const result = await store.reconcileAccount(1, 200);
        expect(result.delta).toBe(50);
        expect(useStore.getState().snapshot!.accounts).toHaveLength(1);
        expect(useStore.getState().snapshot!.transactions.at(-1)).toMatchObject({
            amount: 50,
            source: "adjustment",
        });
    });

    it("creates and deletes both legs of a transfer", async () => {
        const store = useStore.getState();
        const transferId = await store.createTransfer({
            fromAccountId: 1,
            toAccountId: 2,
            amount: 25,
            date: "2026-01-02",
            comment: "move",
        });
        expect(
            useStore.getState().snapshot!.transactions.filter((t) => t.transferId === transferId),
        ).toHaveLength(2);
        await store.deleteTransferWithLegs(transferId);
        expect(useStore.getState().snapshot!.transactions).toHaveLength(1);
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
        expect(useStore.getState().snapshot!.categories.map((c) => c.id)).not.toContain(category);
        expect(useStore.getState().snapshot!.groups.map((g) => g.id)).not.toContain(group);
    });

    it("keeps imports inert and rejects unavailable bank sync in the demo", async () => {
        const store = useStore.getState();
        await expect(store.commitImport([])).resolves.toMatchObject({ demo: true });
        await expect(
            store.createConnection({ bank: "tbank", kind: "api", credentials: {} }),
        ).rejects.toThrow(/not available/i);
        await expect(store.syncConnection(1)).rejects.toThrow(/not available/i);
        await expect(store.submitConnectionSms(1, "1234")).rejects.toThrow(/not available/i);
        await expect(store.deleteConnection(1)).resolves.toBeUndefined();
        await expect(store.cancelConnectionSync(1)).resolves.toBeUndefined();
    });
});

describe("store remote mutations", () => {
    beforeEach(() => {
        window.history.replaceState({}, "", "/app");
        useStore.setState({ snapshot: snapshot(), toast: null, loading: false });
        // fresh spy per test: the counter below is only meaningful if it starts at 0
        useStore.setState({ load: vi.fn().mockResolvedValue(undefined) });
    });

    /** Actions that only edit the snapshot must not spend a round trip on `load`. */
    const refreshCount = () => vi.mocked(useStore.getState().load).mock.calls.length;

    it("sends account edits to their own endpoints and adopts the server id", async () => {
        const createAccount = vi.spyOn(api, "createAccount").mockResolvedValue({ id: 4 });
        const patchAccount = vi.spyOn(api, "patchAccount").mockResolvedValue({});
        const deleteAccount = vi.spyOn(api, "deleteAccount").mockResolvedValue({});
        const s = useStore.getState();

        const id = await s.createAccount({ name: "Cash", openingBalance: 20 });
        expect(id).toBe(4);
        expect(createAccount).toHaveBeenCalledExactlyOnceWith({ name: "Cash", openingBalance: 20 });
        expect(useStore.getState().snapshot!.accounts.at(-1)).toMatchObject({
            id: 4,
            name: "Cash",
            openingBalance: 20,
        });

        await s.patchAccount(4, { name: "Cash 2" });
        expect(patchAccount).toHaveBeenCalledExactlyOnceWith(4, { name: "Cash 2" });

        await s.deleteAccount(4, 1);
        expect(deleteAccount).toHaveBeenCalledExactlyOnceWith(4, 1);
        expect(useStore.getState().snapshot!.accounts.map((a) => a.id)).toEqual([1]);
        expect(refreshCount()).toBe(0);
    });

    it("reloads after a reconcile and returns the server delta", async () => {
        const reconcile = vi.spyOn(api, "reconcileAccount").mockResolvedValue({ delta: 5 });
        const result = await useStore.getState().reconcileAccount(1, 100);
        expect(reconcile).toHaveBeenCalledExactlyOnceWith(1, 100);
        expect(result).toEqual({ delta: 5 });
        expect(refreshCount()).toBe(1);
    });

    it("reloads after creating a transfer but deletes one locally", async () => {
        const create = vi.spyOn(api, "createTransfer").mockResolvedValue({ transferId: "t-9" });
        const remove = vi.spyOn(api, "deleteTransferWithLegs").mockResolvedValue({ deleted: 2 });
        const body = { fromAccountId: 1, toAccountId: 2, amount: 25, date: "2026-01-02" };

        const transferId = await useStore.getState().createTransfer(body);
        expect(create).toHaveBeenCalledExactlyOnceWith(body);
        expect(transferId).toBe("t-9");
        expect(refreshCount()).toBe(1);

        await useStore.getState().deleteTransferWithLegs("t-9");
        expect(remove).toHaveBeenCalledExactlyOnceWith("t-9");
        expect(refreshCount()).toBe(1);
    });

    it("sends category edits to their own endpoints without refreshing", async () => {
        const create = vi.spyOn(api, "createCategory").mockResolvedValue({ id: 5 });
        const patch = vi.spyOn(api, "patchCategory").mockResolvedValue({});
        const remove = vi.spyOn(api, "deleteCategory").mockResolvedValue({});
        const merge = vi.spyOn(api, "mergeCategory").mockResolvedValue({});
        const s = useStore.getState();

        const id = await s.createCategory({ name: "Rent", groupId: 2 });
        expect(id).toBe(5);
        expect(create).toHaveBeenCalledExactlyOnceWith({ name: "Rent", groupId: 2 });

        await s.patchCategory(2, { name: "Food 2" });
        expect(patch).toHaveBeenCalledExactlyOnceWith(2, { name: "Food 2" });

        await s.mergeCategory(5, 2);
        expect(merge).toHaveBeenCalledExactlyOnceWith(5, 2);

        await s.deleteCategory(2);
        expect(remove).toHaveBeenCalledExactlyOnceWith(2);
        expect(useStore.getState().snapshot!.categories.map((c) => c.id)).toEqual([1]);
        expect(refreshCount()).toBe(0);
    });

    it("persists a cross-group move as a group patch plus a global reorder", async () => {
        const patch = vi.spyOn(api, "patchCategory").mockResolvedValue({});
        const reorder = vi.spyOn(api, "reorderCategories").mockResolvedValue({});

        await useStore.getState().moveCategory(2, 1, [2, 1]);
        expect(patch).toHaveBeenCalledExactlyOnceWith(2, { groupId: 1 });
        expect(reorder).toHaveBeenCalledExactlyOnceWith([2, 1]);

        // same group: only the order travels
        await useStore.getState().moveCategory(2, 1, [1, 2]);
        expect(patch).toHaveBeenCalledTimes(1);
        expect(reorder).toHaveBeenLastCalledWith([1, 2]);
        expect(refreshCount()).toBe(0);
    });

    it("reloads and warns when persisting a move fails", async () => {
        vi.spyOn(api, "patchCategory").mockResolvedValue({});
        vi.spyOn(api, "reorderCategories").mockRejectedValue(new Error("offline"));

        await expect(useStore.getState().moveCategory(2, 2, [2, 1])).rejects.toThrow("offline");
        expect(useStore.getState().toast).toMatchObject({
            title: "Failed to move category",
            theme: "danger",
        });
        expect(refreshCount()).toBe(1);
    });

    it("sends group edits to their own endpoints without refreshing", async () => {
        const create = vi.spyOn(api, "createGroup").mockResolvedValue({ id: 6 });
        const patch = vi.spyOn(api, "patchGroup").mockResolvedValue({});
        const remove = vi.spyOn(api, "deleteGroup").mockResolvedValue({});
        const reorder = vi.spyOn(api, "reorderGroups").mockResolvedValue({});
        const s = useStore.getState();

        const id = await s.createGroup({ name: "Fun", kind: "expense" });
        expect(id).toBe(6);
        expect(create).toHaveBeenCalledExactlyOnceWith({ name: "Fun", kind: "expense" });

        await s.patchGroup(2, { name: "Home 2" });
        expect(patch).toHaveBeenCalledExactlyOnceWith(2, { name: "Home 2" });

        await s.reorderGroups([6, 2, 1]);
        expect(reorder).toHaveBeenCalledExactlyOnceWith([6, 2, 1]);
        expect(useStore.getState().snapshot!.groups.find((g) => g.id === 2)!.sort).toBe(2);

        await s.deleteGroup(6);
        expect(remove).toHaveBeenCalledExactlyOnceWith(6);
        expect(useStore.getState().snapshot!.groups.map((g) => g.id)).toEqual([1, 2]);
        expect(refreshCount()).toBe(0);
    });

    it("reloads and warns when persisting a group reorder fails", async () => {
        vi.spyOn(api, "reorderGroups").mockRejectedValue(new Error("offline"));
        await useStore.getState().reorderGroups([2, 1]);
        await vi.waitFor(() => expect(refreshCount()).toBe(1));
        expect(useStore.getState().toast).toMatchObject({
            title: "Failed to reorder groups",
            theme: "danger",
        });
    });

    it("commits an import and reloads with the server result", async () => {
        const commit = vi.spyOn(api, "importCommit").mockResolvedValue({ inserted: 1 });
        const rows = [
            {
                date: "2026-01-01",
                amount: -5,
                description: "Groceries",
                categoryId: null,
                accountId: null,
            },
        ];
        await expect(useStore.getState().commitImport(rows)).resolves.toEqual({ inserted: 1 });
        expect(commit).toHaveBeenCalledExactlyOnceWith(rows);
        expect(refreshCount()).toBe(1);
    });

    it("reloads after every bank-connection call", async () => {
        const create = vi.spyOn(api, "createConnection").mockResolvedValue({ id: 7 });
        const remove = vi.spyOn(api, "deleteConnection").mockResolvedValue({ deleted: 7 });
        const sync = vi.spyOn(api, "syncConnection").mockResolvedValue({ status: "sms" });
        const sms = vi.spyOn(api, "submitConnectionSms").mockResolvedValue({ status: "ok" });
        const cancel = vi.spyOn(api, "cancelConnectionSync").mockResolvedValue({ cancelled: 7 });
        const s = useStore.getState();

        const connection = { bank: "tbank", kind: "api", credentials: {} };
        await expect(s.createConnection(connection)).resolves.toEqual({ id: 7 });
        expect(create).toHaveBeenCalledExactlyOnceWith(connection);
        expect(refreshCount()).toBe(1);

        await expect(s.syncConnection(7)).resolves.toEqual({ status: "sms" });
        expect(sync).toHaveBeenCalledExactlyOnceWith(7);
        expect(refreshCount()).toBe(2);

        await expect(s.submitConnectionSms(7, "1234")).resolves.toEqual({ status: "ok" });
        expect(sms).toHaveBeenCalledExactlyOnceWith(7, "1234");
        expect(refreshCount()).toBe(3);

        await s.cancelConnectionSync(7);
        expect(cancel).toHaveBeenCalledExactlyOnceWith(7);
        expect(refreshCount()).toBe(4);

        await s.deleteConnection(7);
        expect(remove).toHaveBeenCalledExactlyOnceWith(7);
        expect(refreshCount()).toBe(5);
    });
});
