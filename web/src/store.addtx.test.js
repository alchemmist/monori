import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { useStore } from "./store.js";

const tx = (id, date) => ({
    id,
    date,
    amount: -100 * id,
    description: `tx ${id}`,
    accountId: 1,
    categoryId: null,
    hidden: false,
});

beforeEach(() => {
    useStore.setState({
        snapshot: {
            accounts: [{ id: 1, name: "Card" }],
            groups: [],
            categories: [],
            budgets: [],
            connections: [],
            transactions: [tx(1, "2026-01-01T00:00:00"), tx(3, "2026-03-01T00:00:00")],
            transactionsTotal: 2,
        },
        toast: null,
    });
});

afterEach(() => {
    vi.restoreAllMocks();
});

const body = {
    date: "2026-02-01T12:00:00",
    amount: -45000,
    accountId: 1,
    description: "Lenta",
    categoryId: 7,
    comment: "weekly run",
};

describe("addTransaction", () => {
    it("posts the row and merges it into the ledger in date order", async () => {
        vi.spyOn(api, "createTx").mockResolvedValue({ id: 42 });

        const created = await useStore.getState().addTransaction(body);

        expect(api.createTx).toHaveBeenCalledWith(body);
        expect(created.id).toBe(42);
        const s = useStore.getState();
        expect(s.snapshot.transactions.map((t) => t.id)).toEqual([1, 42, 3]);
        expect(s.snapshot.transactionsTotal).toBe(3);
    });

    it("stores the row with the fields the ledger renders", async () => {
        vi.spyOn(api, "createTx").mockResolvedValue({ id: 42 });

        await useStore.getState().addTransaction(body);

        const row = useStore.getState().snapshot.transactions.find((t) => t.id === 42);
        expect(row).toMatchObject({
            date: body.date,
            amount: -45000,
            description: "Lenta",
            accountId: 1,
            categoryId: 7,
            comment: "weekly run",
            source: "manual",
            transferId: null,
            bankCategory: "",
        });
    });

    it("defaults the optional fields when they are left out", async () => {
        vi.spyOn(api, "createTx").mockResolvedValue({ id: 43 });

        await useStore.getState().addTransaction({
            date: "2026-02-02T12:00:00",
            amount: 1000,
            accountId: 1,
        });

        const row = useStore.getState().snapshot.transactions.find((t) => t.id === 43);
        expect(row).toMatchObject({ description: "", comment: "", categoryId: null });
    });

    it("leaves the ledger untouched when the server refuses", async () => {
        vi.spyOn(api, "createTx").mockRejectedValue(new Error("nope"));

        await expect(useStore.getState().addTransaction(body)).rejects.toThrow("nope");

        const s = useStore.getState();
        expect(s.snapshot.transactions.map((t) => t.id)).toEqual([1, 3]);
        expect(s.snapshot.transactionsTotal).toBe(2);
    });
});
