import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { useStore } from "./store.js";
import { buildSnapshot } from "./test/render.js";
import type { Transaction } from "./types.js";

const tx = (id: number, date: string): Transaction => ({
    id,
    date,
    amount: -100 * id,
    description: `tx ${id}`,
    accountId: 1,
    categoryId: null,
    bankCategory: "",
    transferId: null,
    comment: "",
    hidden: false,
});

beforeEach(() => {
    useStore.setState({
        snapshot: buildSnapshot({
            accounts: [{ id: 1, name: "Card" }],
            groups: [],
            categories: [],
            budgets: [],
            connections: [],
            transactions: [tx(1, "2026-01-01T00:00:00"), tx(3, "2026-03-01T00:00:00")],
            transactionsTotal: 2,
        }),
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
        expect(s.snapshot!.transactions.map((t) => t.id)).toEqual([1, 42, 3]);
        expect(s.snapshot!.transactionsTotal).toBe(3);
    });

    it("stores the row with the fields the ledger renders", async () => {
        vi.spyOn(api, "createTx").mockResolvedValue({ id: 42 });

        await useStore.getState().addTransaction(body);

        const row = useStore.getState().snapshot!.transactions.find((t) => t.id === 42);
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

        const row = useStore.getState().snapshot!.transactions.find((t) => t.id === 43);
        expect(row).toMatchObject({ description: "", comment: "", categoryId: null });
    });

    it("leaves the ledger untouched when the server refuses", async () => {
        vi.spyOn(api, "createTx").mockRejectedValue(new Error("nope"));

        await expect(useStore.getState().addTransaction(body)).rejects.toThrow("nope");

        const s = useStore.getState();
        expect(s.snapshot!.transactions.map((t) => t.id)).toEqual([1, 3]);
        expect(s.snapshot!.transactionsTotal).toBe(2);
    });
});

describe("updateTransaction", () => {
    it("patches the row and shows the new value straight away", async () => {
        vi.spyOn(api, "patchTx").mockResolvedValue({ ok: true });

        await useStore.getState().updateTransaction(1, { amount: -5000, comment: "split" });

        expect(api.patchTx).toHaveBeenCalledWith(1, { amount: -5000, comment: "split" });
        const row = useStore.getState().snapshot!.transactions.find((t) => t.id === 1);
        expect(row).toMatchObject({ amount: -5000, comment: "split", description: "tx 1" });
    });

    it("re-sorts the ledger when the date moves the row", async () => {
        vi.spyOn(api, "patchTx").mockResolvedValue({ ok: true });

        await useStore.getState().updateTransaction(1, { date: "2026-04-01T00:00:00" });

        expect(useStore.getState().snapshot!.transactions.map((t) => t.id)).toEqual([3, 1]);
    });

    it("rolls the row back and warns when the server refuses", async () => {
        vi.spyOn(api, "patchTx").mockRejectedValue(new Error("nope"));

        await useStore.getState().updateTransaction(1, { amount: -5000 });

        const s = useStore.getState();
        expect(s.snapshot!.transactions.find((t) => t.id === 1)!.amount).toBe(-100);
        expect(s.toast!.theme).toBe("danger");
    });

    it("rolls back only the failed fields when another edit succeeds", async () => {
        let rejectFirst: (reason?: unknown) => void;
        vi.spyOn(api, "patchTx")
            .mockImplementationOnce(
                () =>
                    new Promise((_, reject) => {
                        rejectFirst = reject;
                    }),
            )
            .mockResolvedValueOnce({ ok: true });

        const first = useStore.getState().updateTransaction(1, { amount: -5000 });
        await useStore.getState().updateTransaction(1, { comment: "kept" });
        rejectFirst!(new Error("nope"));
        await first;

        expect(useStore.getState().snapshot!.transactions.find((t) => t.id === 1)).toMatchObject({
            amount: -100,
            comment: "kept",
        });
    });

    it("keeps a newer edit to the same field when an older request fails", async () => {
        let rejectFirst: (reason?: unknown) => void;
        vi.spyOn(api, "patchTx")
            .mockImplementationOnce(
                () =>
                    new Promise((_, reject) => {
                        rejectFirst = reject;
                    }),
            )
            .mockResolvedValueOnce({ ok: true });

        const first = useStore.getState().updateTransaction(1, { amount: -5000 });
        await useStore.getState().updateTransaction(1, { amount: -7500 });
        rejectFirst!(new Error("nope"));
        await first;

        expect(useStore.getState().snapshot!.transactions.find((t) => t.id === 1)!.amount).toBe(
            -7500,
        );
    });

    it("ignores an id that is not in the ledger", async () => {
        vi.spyOn(api, "patchTx").mockResolvedValue({ ok: true });

        await useStore.getState().updateTransaction(999, { amount: 1 });

        expect(api.patchTx).not.toHaveBeenCalled();
        expect(useStore.getState().snapshot!.transactions).toHaveLength(2);
    });
});

describe("replaceTransactionSplits", () => {
    it("preserves a newer transaction edit when split rollback runs", async () => {
        let rejectSplit: (reason?: unknown) => void;
        vi.spyOn(api, "replaceTxSplits").mockImplementation(
            () =>
                new Promise((_, reject) => {
                    rejectSplit = reject;
                }),
        );
        vi.spyOn(api, "patchTx").mockResolvedValue({ ok: true });

        const split = useStore.getState().replaceTransactionSplits(1, [
            { categoryId: 2, amount: -50, comment: "first" },
            { categoryId: 3, amount: -50, comment: "second" },
        ]);
        await useStore.getState().updateTransaction(1, { comment: "keep me" });
        rejectSplit!(new Error("offline"));
        await expect(split).rejects.toThrow("offline");

        expect(
            useStore.getState().snapshot!.transactions.find((row) => row.id === 1),
        ).toMatchObject({
            comment: "keep me",
            categoryId: null,
            splits: [],
        });
    });

    it("preserves the current category when the server confirms split removal", async () => {
        useStore.setState((state) => ({
            snapshot: {
                ...state.snapshot!,
                transactions: state.snapshot!.transactions.map((row) =>
                    row.id === 1
                        ? {
                              ...row,
                              categoryId: 2,
                              splits: [{ id: 9, categoryId: 2, amount: row.amount, comment: "" }],
                          }
                        : row,
                ),
            },
        }));
        vi.spyOn(api, "replaceTxSplits").mockResolvedValue({ splits: [] });

        await useStore.getState().replaceTransactionSplits(1, []);

        expect(
            useStore.getState().snapshot!.transactions.find((row) => row.id === 1),
        ).toMatchObject({
            categoryId: 2,
            splits: [],
        });
    });
});

describe("deleteTransaction", () => {
    it("drops the row and its count", async () => {
        vi.spyOn(api, "deleteTx").mockResolvedValue({ ok: true });

        await expect(useStore.getState().deleteTransaction(1)).resolves.toBe(true);

        expect(api.deleteTx).toHaveBeenCalledWith(1);
        const s = useStore.getState();
        expect(s.snapshot!.transactions.map((t) => t.id)).toEqual([3]);
        expect(s.snapshot!.transactionsTotal).toBe(1);
    });

    it("puts the row back in order when the server refuses", async () => {
        vi.spyOn(api, "deleteTx").mockRejectedValue(new Error("nope"));

        await expect(useStore.getState().deleteTransaction(1)).resolves.toBe(false);

        const s = useStore.getState();
        expect(s.snapshot!.transactions.map((t) => t.id)).toEqual([1, 3]);
        expect(s.snapshot!.transactionsTotal).toBe(2);
        expect(s.toast!.theme).toBe("danger");
    });
});
