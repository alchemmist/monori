import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { useStore } from "./store.js";
import { buildSnapshot } from "./test/render.js";

const base = () =>
    buildSnapshot({
        accounts: [
            { id: 1, name: "Card", openingBalance: 100, archived: false, sort: 1 },
            { id: 5, name: "Cash", openingBalance: 0, archived: false, sort: 2 },
        ],
        groups: [
            { id: 1, name: "Income", kind: "income", sort: 1 },
            { id: 2, name: "Home", kind: "expense", sort: 2 },
        ],
        categories: [
            { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
            { id: 4, groupId: 2, name: "Food", keywords: "shop", sort: 2, archived: false },
        ],
        budgets: [
            { categoryId: 4, year: 2026, month: 1, amount: 20 },
            { categoryId: 4, year: 2026, month: 2, amount: 30 },
            { categoryId: 4, year: 2025, month: 1, amount: 40 },
            { categoryId: 1, year: 2026, month: 1, amount: 50 },
        ],
        transactions: [
            {
                id: 2,
                date: "2026-01-01",
                amount: 50,
                accountId: 1,
                categoryId: 1,
                transferId: null,
            },
            {
                id: 7,
                date: "2026-01-02",
                amount: -10,
                accountId: 5,
                categoryId: 4,
                transferId: null,
            },
        ],
        connections: [],
    });

const snap = () => useStore.getState().snapshot!;

beforeEach(() => {
    window.history.replaceState({}, "", "/demo");
    useStore.setState({ snapshot: base(), toast: null, tabs: [], loading: false });
});

afterEach(() => {
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
});

describe("setBudget", () => {
    it("replaces only the cell for that exact category, year and month", () => {
        void useStore.getState().setBudget(4, 2026, 1, 99);
        expect(snap().budgets).toEqual([
            { categoryId: 4, year: 2026, month: 2, amount: 30 },
            { categoryId: 4, year: 2025, month: 1, amount: 40 },
            { categoryId: 1, year: 2026, month: 1, amount: 50 },
            { categoryId: 4, year: 2026, month: 1, amount: 99 },
        ]);
    });

    it("drops the cell instead of storing a zero", () => {
        void useStore.getState().setBudget(4, 2026, 1, 0);
        expect(snap().budgets).toEqual([
            { categoryId: 4, year: 2026, month: 2, amount: 30 },
            { categoryId: 4, year: 2025, month: 1, amount: 40 },
            { categoryId: 1, year: 2026, month: 1, amount: 50 },
        ]);
    });

    it("appends a cell that did not exist yet and leaves the rest untouched", () => {
        void useStore.getState().setBudget(1, 2026, 3, 7);
        expect(snap().budgets).toEqual([
            ...base().budgets,
            { categoryId: 1, year: 2026, month: 3, amount: 7 },
        ]);
    });

    it("never calls the API in the demo", async () => {
        const put = vi.spyOn(api, "putBudget");
        await useStore.getState().setBudget(4, 2026, 1, 99);
        expect(put).not.toHaveBeenCalled();
    });
});

describe("setTxCategory and setTxAccount in the demo", () => {
    it("retags only the matching transaction", () => {
        useStore.getState().setTxCategory(7, 9);
        expect(snap().transactions.map((t) => [t.id, t.categoryId])).toEqual([
            [2, 1],
            [7, 9],
        ]);
    });

    it("moves only the matching transaction", () => {
        useStore.getState().setTxAccount(7, 9);
        expect(snap().transactions.map((t) => [t.id, t.accountId])).toEqual([
            [2, 1],
            [7, 9],
        ]);
    });

    it("leaves every row alone when no id matches", () => {
        useStore.getState().setTxCategory(999, 1);
        expect(snap().transactions).toEqual(base().transactions);
    });

    it("never calls the API in the demo", () => {
        const patch = vi.spyOn(api, "patchTx");
        useStore.getState().setTxCategory(7, 1);
        useStore.getState().setTxAccount(7, 1);
        expect(patch).not.toHaveBeenCalled();
    });
});

describe("createAccount in the demo", () => {
    it("takes the next id past the highest one and fills every default", async () => {
        const id = await useStore.getState().createAccount({ name: "Wallet" });
        expect(id).toBe(6);
        expect(snap().accounts.at(-1)).toEqual({
            id: 6,
            name: "Wallet",
            type: "other",
            icon: "wallet",
            color: "#5b6472",
            iconImage: null,
            currency: "RUB",
            sort: 1e9,
            archived: false,
            openingBalance: 0,
            openingDate: null,
        });
    });

    it("keeps every field the caller supplied", async () => {
        const id = await useStore.getState().createAccount({
            name: "Deposit",
            type: "savings",
            icon: "piggy",
            color: "#ff0000",
            iconImage: "img.png",
            currency: "USD",
            openingBalance: 500,
            openingDate: "2026-02-01",
        });
        expect(snap().accounts.at(-1)).toEqual({
            id,
            name: "Deposit",
            type: "savings",
            icon: "piggy",
            color: "#ff0000",
            iconImage: "img.png",
            currency: "USD",
            sort: 1e9,
            archived: false,
            openingBalance: 500,
            openingDate: "2026-02-01",
        });
    });

    it("normalises an empty icon image to null", async () => {
        await useStore.getState().createAccount({ name: "Wallet", iconImage: "" });
        expect(snap().accounts.at(-1)!.iconImage).toBeNull();
    });
});

describe("patchAccount and deleteAccount in the demo", () => {
    it("patches only the named account", async () => {
        await useStore.getState().patchAccount(5, { name: "Pocket", archived: true });
        expect(snap().accounts).toEqual([
            base().accounts[0],
            { ...base().accounts[1], name: "Pocket", archived: true },
        ]);
    });

    it("removes the account and reassigns only its own transactions", async () => {
        await useStore.getState().deleteAccount(5, 9);
        expect(snap().accounts.map((a) => a.id)).toEqual([1]);
        expect(snap().transactions.map((t) => [t.id, t.accountId])).toEqual([
            [2, 1],
            [7, 9],
        ]);
    });

    it("leaves the transactions exactly as they were with no reassign target", async () => {
        await useStore.getState().deleteAccount(5);
        expect(snap().accounts.map((a) => a.id)).toEqual([1]);
        expect(snap().transactions).toEqual(base().transactions);
    });
});

describe("reconcileAccount in the demo", () => {
    it("books an adjustment for the gap between the actual and the derived balance", async () => {
        const result = await useStore.getState().reconcileAccount(1, 200);
        expect(result).toEqual({ delta: 50 });
        const added = snap().transactions.at(-1);
        expect(added).toEqual({
            id: 8,
            date: added!.date,
            amount: 50,
            description: "Reconcile adjustment",
            bankCategory: "",
            mcc: "",
            categoryId: null,
            accountId: 1,
            transferId: null,
            comment: "",
            source: "adjustment",
        });
        // seconds precision, no milliseconds and no trailing Z
        expect(added!.date).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/);
    });

    it("adds nothing when the balance already matches", async () => {
        const result = await useStore.getState().reconcileAccount(1, 150);
        expect(result).toEqual({ delta: 0 });
        expect(snap().transactions).toEqual(base().transactions);
    });

    it("treats an unknown account as a zero balance", async () => {
        const result = await useStore.getState().reconcileAccount(42, 30);
        expect(result).toEqual({ delta: 30 });
        expect(snap().transactions.at(-1)).toMatchObject({ amount: 30, accountId: 42 });
    });

    it("counts an absent opening balance as zero", async () => {
        useStore.setState({
            snapshot: {
                ...base(),
                accounts: [{ id: 1, name: "Card" } as ReturnType<typeof base>["accounts"][number]],
                transactions: [],
            },
        });
        const result = await useStore.getState().reconcileAccount(1, 25);
        expect(result).toEqual({ delta: 25 });
    });
});

describe("createTransfer and deleteTransfer in the demo", () => {
    it("books two consecutive legs with mirrored amounts", async () => {
        const transferId = await useStore
            .getState()
            .createTransfer({ fromAccountId: 1, toAccountId: 5, amount: 25, date: "2026-03-01" });
        expect(transferId).toBe("demo-8");
        expect(snap().transactions.slice(2)).toEqual([
            {
                id: 8,
                date: "2026-03-01",
                amount: -25,
                description: "Transfer",
                bankCategory: "",
                mcc: "",
                categoryId: null,
                accountId: 1,
                transferId: "demo-8",
                comment: "",
                source: "transfer",
            },
            {
                id: 9,
                date: "2026-03-01",
                amount: 25,
                description: "Transfer",
                bankCategory: "",
                mcc: "",
                categoryId: null,
                accountId: 5,
                transferId: "demo-8",
                comment: "",
                source: "transfer",
            },
        ]);
    });

    it("carries the comment onto both legs", async () => {
        await useStore.getState().createTransfer({
            fromAccountId: 1,
            toAccountId: 5,
            amount: 25,
            date: "2026-03-01",
            comment: "rent",
        });
        expect(
            snap()
                .transactions.slice(2)
                .map((t) => t.comment),
        ).toEqual(["rent", "rent"]);
    });

    it("deletes only the legs of that transfer", async () => {
        const transferId = await useStore
            .getState()
            .createTransfer({ fromAccountId: 1, toAccountId: 5, amount: 25, date: "2026-03-01" });
        await useStore.getState().createTransfer({
            fromAccountId: 5,
            toAccountId: 1,
            amount: 5,
            date: "2026-03-02",
        });
        await useStore.getState().deleteTransferWithLegs(transferId);
        expect(snap().transactions.map((t) => t.id)).toEqual([2, 7, 10, 11]);
    });
});

describe("createCategory in the demo", () => {
    it("takes the next id past the highest one and fills the defaults", async () => {
        const id = await useStore.getState().createCategory({ name: "Rent", groupId: 2 });
        expect(id).toBe(5);
        expect(snap().categories.at(-1)).toEqual({
            id: 5,
            groupId: 2,
            name: "Rent",
            keywords: "",
            sort: 1e9,
            archived: false,
        });
    });

    it("keeps the keywords the caller supplied", async () => {
        await useStore.getState().createCategory({ name: "Rent", groupId: 2, keywords: "flat" });
        expect(snap().categories.at(-1)!.keywords).toBe("flat");
    });
});

describe("patchCategory", () => {
    it("applies only the fields present in the patch, on the named category", async () => {
        await useStore.getState().patchCategory(4, { name: "Groceries" });
        expect(snap().categories).toEqual([
            base().categories[0],
            { ...base().categories[1], name: "Groceries" },
        ]);
    });

    it("applies every supported field at once", async () => {
        await useStore
            .getState()
            .patchCategory(4, { name: "Groceries", groupId: 1, keywords: "food", archived: true });
        expect(snap().categories[1]).toEqual({
            id: 4,
            groupId: 1,
            name: "Groceries",
            keywords: "food",
            sort: 2,
            archived: true,
        });
    });

    it("ignores omitted fields rather than blanking them", async () => {
        await useStore.getState().patchCategory(4, { archived: false });
        expect(snap().categories[1]).toEqual({ ...base().categories[1], archived: false });
    });

    it("keeps a falsy-but-present value", async () => {
        await useStore.getState().patchCategory(4, { keywords: "", groupId: 0, name: "" });
        expect(snap().categories[1]).toEqual({
            id: 4,
            groupId: 0,
            name: "",
            keywords: "",
            sort: 2,
            archived: false,
        });
    });
});

describe("deleteCategory in the demo", () => {
    it("removes the category, its budgets and unfiles only its transactions", async () => {
        await useStore.getState().deleteCategory(4);
        expect(snap().categories.map((c) => c.id)).toEqual([1]);
        expect(snap().budgets).toEqual([{ categoryId: 1, year: 2026, month: 1, amount: 50 }]);
        expect(snap().transactions.map((t) => [t.id, t.categoryId])).toEqual([
            [2, 1],
            [7, null],
        ]);
    });

    it("never calls the API in the demo", async () => {
        const remove = vi.spyOn(api, "deleteCategory");
        await useStore.getState().deleteCategory(4);
        expect(remove).not.toHaveBeenCalled();
    });
});

describe("moveCategory in the demo", () => {
    it("regroups the dropped card and renumbers sort by the given order", async () => {
        await useStore.getState().moveCategory(4, 1, [4, 1]);
        expect(snap().categories).toEqual([
            { ...base().categories[0], sort: 2 },
            { ...base().categories[1], groupId: 1, sort: 1 },
        ]);
    });

    it("keeps the existing sort for a category the order leaves out", async () => {
        await useStore.getState().moveCategory(4, 2, [4]);
        expect(snap().categories.map((c) => [c.id, c.sort])).toEqual([
            [1, 1],
            [4, 1],
        ]);
    });

    it("never calls the API in the demo", async () => {
        const patch = vi.spyOn(api, "patchCategory");
        const reorder = vi.spyOn(api, "reorderCategories");
        await useStore.getState().moveCategory(4, 1, [4, 1]);
        expect(patch).not.toHaveBeenCalled();
        expect(reorder).not.toHaveBeenCalled();
    });
});

describe("groups in the demo", () => {
    it("takes the next id past the highest one when creating", async () => {
        const id = await useStore.getState().createGroup({ name: "Fun", kind: "expense" });
        expect(id).toBe(3);
        expect(snap().groups.at(-1)).toEqual({ id: 3, name: "Fun", kind: "expense", sort: 1e9 });
    });

    it("patches only the named group", async () => {
        await useStore.getState().patchGroup(2, { name: "House" });
        expect(snap().groups).toEqual([base().groups[0], { ...base().groups[1], name: "House" }]);
    });

    it("removes only the named group", async () => {
        await useStore.getState().deleteGroup(1);
        expect(snap().groups).toEqual([base().groups[1]]);
    });

    it("renumbers sort by the given order and keeps the rest", async () => {
        await useStore.getState().reorderGroups([2]);
        expect(snap().groups.map((g) => [g.id, g.sort])).toEqual([
            [1, 1],
            [2, 1],
        ]);
    });
});
