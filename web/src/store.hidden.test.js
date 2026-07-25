import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { useStore } from "./store.js";

const tx = (id, date = "2026-01-05T00:00:00") => ({
    id,
    date,
    amount: -100 * id,
    description: `tx ${id}`,
    hidden: false,
});

beforeEach(() => {
    useStore.setState({
        snapshot: {
            accounts: [],
            groups: [],
            categories: [],
            budgets: [],
            connections: [],
            transactions: [tx(1, "2026-01-01T00:00:00"), tx(2), tx(3, "2026-02-01T00:00:00")],
            transactionsTotal: 3,
        },
        hiddenTx: null,
        toast: null,
    });
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("hiding transactions", () => {
    it("hideTx moves the row out of the snapshot and patches the server", () => {
        vi.spyOn(api, "patchTx").mockResolvedValue({});

        useStore.getState().hideTx(2);

        const s = useStore.getState();
        expect(s.snapshot.transactions.map((t) => t.id)).toEqual([1, 3]);
        expect(s.snapshot.transactionsTotal).toBe(2);
        expect(s.hiddenTx.map((t) => t.id)).toEqual([2]);
        expect(s.hiddenTx[0].hidden).toBe(true);
        expect(api.patchTx).toHaveBeenCalledWith(2, { hidden: true });
    });

    it("unhideTx puts the row back in canonical date order", () => {
        vi.spyOn(api, "patchTx").mockResolvedValue({});

        useStore.getState().hideTx(2);
        useStore.getState().unhideTx(2);

        const s = useStore.getState();
        expect(s.snapshot.transactions.map((t) => t.id)).toEqual([1, 2, 3]);
        expect(s.snapshot.transactions[1].hidden).toBe(false);
        expect(s.snapshot.transactionsTotal).toBe(3);
        expect(s.hiddenTx).toEqual([]);
        expect(api.patchTx).toHaveBeenLastCalledWith(2, { hidden: false });
    });

    it("hiding an unknown id is a no-op", () => {
        const patch = vi.spyOn(api, "patchTx").mockResolvedValue({});

        useStore.getState().hideTx(99);
        useStore.getState().unhideTx(99);

        expect(useStore.getState().snapshot.transactions).toHaveLength(3);
        expect(patch).not.toHaveBeenCalled();
    });

    it("loadHiddenTx replaces the local list with the server truth", async () => {
        vi.spyOn(api, "hiddenTx").mockResolvedValue({
            total: 1,
            rows: [{ ...tx(9), hidden: true }],
        });

        await useStore.getState().loadHiddenTx();

        expect(useStore.getState().hiddenTx.map((t) => t.id)).toEqual([9]);
    });

    it("a failed hide patch surfaces a toast", async () => {
        vi.spyOn(api, "patchTx").mockRejectedValue(new Error("network down"));

        useStore.getState().hideTx(2);
        await vi.waitFor(() => expect(useStore.getState().toast).toBeTruthy());

        expect(useStore.getState().toast.title).toMatch(/hide/i);
    });
});
