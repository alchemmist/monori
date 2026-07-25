import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { TX_CHUNK, useStore } from "./store.js";

// one shared timestamp, so the canonical order falls back to id and the ledger
// reads as ids 1..n ascending however the chunks arrive
const tx = (id) => ({ id, date: "2026-01-01T00:00:00" });

/** The ledger the fake server holds, newest-first like GET /api/transactions. */
const ledger = (n) => Array.from({ length: n }, (_, i) => tx(n - i)); // ids n..1, newest first

const stubServer = (total, lightWindow) => {
    const rows = ledger(total);
    vi.spyOn(api, "snapshot").mockResolvedValue({
        accounts: [],
        groups: [],
        categories: [],
        budgets: [],
        connections: [],
        transactions: [...rows.slice(0, lightWindow)].reverse(),
        transactionsTotal: total,
    });
    vi.spyOn(api, "transactions").mockImplementation(async ({ limit, offset }) => ({
        total,
        rows: rows.slice(offset, offset + limit),
    }));
};

beforeEach(() => {
    useStore.setState({ snapshot: null, loading: true, error: null, txProgress: null });
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("progressive transaction loading", () => {
    it("paints on the light snapshot, then fills the rest in canonical order", async () => {
        stubServer(TX_CHUNK * 2 + 5, 3);

        await useStore.getState().load();
        // the app is interactive on the light snapshot alone; the fill is async
        expect(useStore.getState().loading).toBe(false);
        expect(api.snapshot).toHaveBeenCalledWith({ light: true });

        await vi.waitFor(() => expect(useStore.getState().txProgress).toBeNull());
        const ids = useStore.getState().snapshot.transactions.map((t) => t.id);
        expect(ids).toEqual([...ids].sort((a, b) => a - b));
        expect(ids).toHaveLength(TX_CHUNK * 2 + 5);
    });

    it("coalesces fast chunks into one snapshot write but still ticks progress", async () => {
        stubServer(TX_CHUNK * 3 + 7, 5);
        const snapshots = new Set();
        const progress = [];
        const unsub = useStore.subscribe((s) => {
            if (s.snapshot) snapshots.add(s.snapshot);
            if (s.txProgress) progress.push(s.txProgress.loaded);
        });

        await useStore.getState().load();
        await vi.waitFor(() => expect(useStore.getState().txProgress).toBeNull());
        unsub();

        // the mocked chunks land inside one flush window: the light snapshot and
        // a single merged write, not one write per chunk
        expect(snapshots.size).toBe(2);
        expect(progress).toEqual([5, TX_CHUNK + 5, TX_CHUNK * 2 + 5, TX_CHUNK * 3 + 5]);
        expect(useStore.getState().snapshot.transactions).toHaveLength(TX_CHUNK * 3 + 7);
    });

    it("reports progress while the fill runs and clears it at the end", async () => {
        stubServer(10, 2);
        const seen = [];
        const unsub = useStore.subscribe((s) => seen.push(s.txProgress));

        await useStore.getState().load();
        await vi.waitFor(() => expect(useStore.getState().txProgress).toBeNull());
        unsub();

        const running = seen.filter(Boolean);
        expect(running.length).toBeGreaterThan(0);
        expect(running.every((p) => p.total === 10 && p.loaded < p.total)).toBe(true);
    });

    it("skips the fill entirely when the light snapshot already has everything", async () => {
        stubServer(4, 4);

        await useStore.getState().load();

        expect(api.transactions).not.toHaveBeenCalled();
        expect(useStore.getState().txProgress).toBeNull();
    });

    it("keeps an optimistic edit made while a chunk was in flight", async () => {
        stubServer(TX_CHUNK + 2, 1);
        vi.spyOn(api, "patchTx").mockResolvedValue({});

        await useStore.getState().load();
        const editable = useStore.getState().snapshot.transactions[0].id;
        useStore.getState().setTxCategory(editable, 7);
        await vi.waitFor(() => expect(useStore.getState().txProgress).toBeNull());

        const row = useStore.getState().snapshot.transactions.find((t) => t.id === editable);
        expect(row.categoryId).toBe(7);
    });

    it("drops a stale fill when a reload supersedes it", async () => {
        stubServer(TX_CHUNK + 50, 1);

        const first = useStore.getState().load();
        await first;
        const stale = useStore.getState().fillTransactions();
        await useStore.getState().load();
        await stale;
        await vi.waitFor(() => expect(useStore.getState().txProgress).toBeNull());

        const ids = useStore.getState().snapshot.transactions.map((t) => t.id);
        expect(new Set(ids).size).toBe(ids.length);
    });

    it("surfaces a fill failure as a toast without losing what loaded", async () => {
        stubServer(TX_CHUNK + 2, 2);
        api.transactions.mockRejectedValue(new Error("network down"));

        await useStore.getState().load();
        await vi.waitFor(() => expect(useStore.getState().toast).toBeTruthy());

        expect(useStore.getState().txProgress).toBeNull();
        expect(useStore.getState().snapshot.transactions).toHaveLength(2);
        expect(useStore.getState().error).toBeNull();
    });
});
