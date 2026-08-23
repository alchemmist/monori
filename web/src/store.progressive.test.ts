import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { TX_CHUNK, TX_FLUSH_MS, useStore } from "./store.js";
import { buildSnapshot, tx as makeTx } from "./test/render.js";
import type { Snapshot, Transaction } from "./types.js";

// one shared timestamp, so the canonical order falls back to id and the ledger
// reads as ids 1..n ascending however the chunks arrive
const tx = (id: number): Transaction => makeTx(id, { date: "2026-01-01T00:00:00" });

/** The ledger the fake server holds, newest-first like GET /api/transactions. */
const ledger = (n: number) => Array.from({ length: n }, (_, i) => tx(n - i)); // ids n..1, newest first

const stubServer = (total: number, lightWindow: number) => {
    const rows = ledger(total);
    vi.spyOn(api, "snapshot").mockResolvedValue(
        buildSnapshot({
            accounts: [],
            groups: [],
            categories: [],
            budgets: [],
            connections: [],
            transactions: [...rows.slice(0, lightWindow)].reverse(),
            transactionsTotal: total,
        }),
    );
    vi.spyOn(api, "transactions").mockImplementation(
        async ({ limit = total, offset = 0 } = {}) => ({
            total,
            rows: rows.slice(offset, offset + limit),
        }),
    );
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
        const ids = useStore.getState().snapshot!.transactions.map((t) => t.id);
        expect(ids).toEqual([...ids].sort((a, b) => a - b));
        expect(ids).toHaveLength(TX_CHUNK * 2 + 5);
    });

    it("coalesces fast chunks into one snapshot write but still ticks progress", async () => {
        stubServer(TX_CHUNK * 3 + 7, 5);
        const snapshots = new Set<Snapshot>();
        const progress: number[] = [];
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
        expect(useStore.getState().snapshot!.transactions).toHaveLength(TX_CHUNK * 3 + 7);
    });

    it("reports progress while the fill runs and clears it at the end", async () => {
        stubServer(10, 2);
        const seen: Array<{ loaded: number; total: number } | null> = [];
        const unsub = useStore.subscribe((s) => seen.push(s.txProgress));

        await useStore.getState().load();
        await vi.waitFor(() => expect(useStore.getState().txProgress).toBeNull());
        unsub();

        const running = seen.filter(Boolean);
        expect(running.length).toBeGreaterThan(0);
        expect(running.every((p) => p!.total === 10 && p!.loaded < p!.total)).toBe(true);
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
        const editable = useStore.getState().snapshot!.transactions[0]!.id;
        useStore.getState().setTxCategory(editable, 7);
        await vi.waitFor(() => expect(useStore.getState().txProgress).toBeNull());

        const row = useStore.getState().snapshot!.transactions.find((t) => t.id === editable);
        expect(row!.categoryId).toBe(7);
    });

    it("drops a stale fill when a reload supersedes it", async () => {
        stubServer(TX_CHUNK + 50, 1);

        const first = useStore.getState().load();
        await first;
        const stale = useStore.getState().fillTransactions();
        await useStore.getState().load();
        await stale;
        await vi.waitFor(() => expect(useStore.getState().txProgress).toBeNull());

        const ids = useStore.getState().snapshot!.transactions.map((t) => t.id);
        expect(new Set(ids).size).toBe(ids.length);
    });

    it("throws away the page a superseded fill was still holding", async () => {
        let release: () => void;
        vi.spyOn(api, "transactions").mockImplementation(
            () => new Promise((r) => (release = () => r({ total: 3, rows: [tx(99)] }))),
        );
        useStore.setState({
            snapshot: buildSnapshot({ transactions: [tx(1)], transactionsTotal: 3 }),
            loading: false,
            txProgress: null,
        });

        const stale = useStore.getState().fillTransactions();
        await vi.waitFor(() => expect(useStore.getState().txProgress).not.toBeNull());
        // a reload lands mid-flight and takes the generation with it
        vi.spyOn(api, "snapshot").mockResolvedValue(
            buildSnapshot({
                transactions: [tx(1), tx(2)],
                transactionsTotal: 2,
            }),
        );
        await useStore.getState().load();
        release!();
        await stale;

        // the stale page (id 99) must not reach the snapshot the reload installed
        expect(useStore.getState().snapshot!.transactions.map((t) => t.id)).toEqual([1, 2]);
    });

    it("surfaces a fill failure as a toast without losing what loaded", async () => {
        stubServer(TX_CHUNK + 2, 2);
        vi.mocked(api.transactions).mockRejectedValue(new Error("network down"));

        await useStore.getState().load();
        await vi.waitFor(() => expect(useStore.getState().toast).toBeTruthy());

        expect(useStore.getState().toast).toEqual({
            title: "Failed to load older transactions",
            theme: "danger",
            content: "Error: network down",
        });
        expect(useStore.getState().txProgress).toBeNull();
        expect(useStore.getState().snapshot!.transactions).toHaveLength(2);
        expect(useStore.getState().error).toBeNull();
    });

    it("stays silent when a superseded fill is the one that fails", async () => {
        // the page rejects only once the reload has already taken the generation
        let reject: () => void;
        vi.spyOn(api, "transactions").mockImplementationOnce(
            () => new Promise((_, r) => (reject = () => r(new Error("network down")))),
        );
        vi.spyOn(api, "snapshot").mockResolvedValue(
            buildSnapshot({
                transactions: [tx(1), tx(2)],
                transactionsTotal: 2,
            }),
        );
        useStore.setState({
            snapshot: buildSnapshot({ transactions: [tx(1)], transactionsTotal: 3 }),
            loading: false,
            toast: null,
            txProgress: null,
        });

        const stale = useStore.getState().fillTransactions();
        await vi.waitFor(() => expect(useStore.getState().txProgress).not.toBeNull());
        await useStore.getState().load();
        const progressAfterReload = useStore.getState().txProgress;
        reject!();
        await stale;

        // a stale failure warns nobody and does not touch the live fill's progress
        expect(useStore.getState().toast).toBeNull();
        expect(useStore.getState().txProgress).toEqual(progressAfterReload);
    });
});

describe("load", () => {
    beforeEach(() => {
        window.history.replaceState({}, "", "/app");
    });
    afterEach(() => {
        window.history.replaceState({}, "", "/");
    });

    it("records a failed snapshot fetch as an error and never starts the fill", async () => {
        vi.spyOn(api, "snapshot").mockRejectedValue(new Error("boom"));
        const transactions = vi.spyOn(api, "transactions");
        useStore.setState({ txProgress: { loaded: 1, total: 9 } });

        await useStore.getState().load();

        expect(useStore.getState()).toMatchObject({
            error: "Error: boom",
            loading: false,
            txProgress: null,
        });
        expect(transactions).not.toHaveBeenCalled();
    });

    it("discards a light snapshot whose load was already superseded", async () => {
        const first = buildSnapshot({ transactions: [tx(1)], transactionsTotal: 1 });
        const second = buildSnapshot({ transactions: [tx(2)], transactionsTotal: 1 });
        vi.spyOn(api, "transactions").mockResolvedValue({ total: 1, rows: [] });
        let release: () => void;
        vi.spyOn(api, "snapshot")
            .mockImplementationOnce(() => new Promise((r) => (release = () => r(first))))
            .mockResolvedValue(second);

        const stale = useStore.getState().load();
        await useStore.getState().load();
        release!();
        await stale;

        expect(useStore.getState().snapshot!.transactions[0]!.id).toBe(2);
    });

    it("serves the demo snapshot without any network call", async () => {
        window.history.replaceState({}, "", "/demo");
        const snapshot = vi.spyOn(api, "snapshot");
        useStore.setState({ error: "stale", txProgress: { loaded: 1, total: 9 } });

        await useStore.getState().load();

        expect(snapshot).not.toHaveBeenCalled();
        expect(useStore.getState()).toMatchObject({
            loading: false,
            error: null,
            txProgress: null,
        });
        const s = useStore.getState().snapshot;
        expect(s!.transactionsTotal).toBe(s!.transactions.length);
    });
});

describe("fillTransactions", () => {
    it("does nothing at all without a snapshot to fill", async () => {
        const transactions = vi.spyOn(api, "transactions");
        useStore.setState({ snapshot: null, txProgress: { loaded: 1, total: 9 } });

        await useStore.getState().fillTransactions();

        expect(transactions).not.toHaveBeenCalled();
        // an early return leaves the progress it found, it does not clear it
        expect(useStore.getState().txProgress).toEqual({ loaded: 1, total: 9 });
    });

    it("keeps the true row count when the server under-reports the total", async () => {
        // rows land locally while the page is in flight, so the merged ledger
        // ends up longer than the count the fill was working towards
        const local = [tx(50)];
        vi.spyOn(api, "transactions").mockImplementation(async () => {
            useStore.setState({
                snapshot: {
                    ...useStore.getState().snapshot!,
                    transactions: [...local, tx(60), tx(61), tx(62)],
                },
            });
            return { total: 2, rows: [tx(1)] };
        });
        useStore.setState({
            snapshot: buildSnapshot({ transactions: local, transactionsTotal: 2 }),
            loading: false,
        });

        await useStore.getState().fillTransactions();

        expect(useStore.getState().snapshot!.transactions.map((t) => t.id)).toEqual([
            1, 50, 60, 61, 62,
        ]);
        expect(useStore.getState().snapshot!.transactionsTotal).toBe(5);
        expect(useStore.getState().txProgress).toBeNull();
    });

    it("stops on a short page even while the reported total is still higher", async () => {
        // the reported total never comes down, so the short page is the only
        // signal that the ledger is exhausted; the fake server refuses to serve
        // a second page so a fill that ignores it fails instead of spinning
        const transactions = vi.spyOn(api, "transactions").mockImplementation(async () => {
            if (transactions.mock.calls.length > 1) throw new Error("asked for a page too many");
            return { total: 10_000, rows: ledger(TX_CHUNK - 1) };
        });
        useStore.setState({
            snapshot: buildSnapshot({ transactions: [], transactionsTotal: 10_000 }),
            loading: false,
            toast: null,
        });

        await useStore.getState().fillTransactions();

        expect(transactions).toHaveBeenCalledExactlyOnceWith({ limit: TX_CHUNK, offset: 0 });
        expect(useStore.getState().toast).toBeNull();
        expect(useStore.getState().txProgress).toBeNull();
        expect(useStore.getState().snapshot!.transactions).toHaveLength(TX_CHUNK - 1);
    });

    it("lands a mid-fill flush once the chunks outlive the flush window", async () => {
        const rows = ledger(TX_CHUNK * 2);
        vi.spyOn(api, "transactions").mockImplementation(
            async ({ limit = TX_CHUNK, offset = 0 } = {}) => ({
                total: TX_CHUNK * 2,
                rows: rows.slice(offset, offset + limit),
            }),
        );
        // a slow link: every reading of the clock is a further TX_FLUSH_MS on,
        // so the first chunk is already past its window when the second arrives
        let clock = 0;
        vi.spyOn(performance, "now").mockImplementation(() => (clock += TX_FLUSH_MS));
        useStore.setState({
            snapshot: buildSnapshot({ transactions: [], transactionsTotal: TX_CHUNK * 2 }),
            loading: false,
        });
        const writes: number[] = [];
        const unsub = useStore.subscribe((s) => writes.push(s.snapshot?.transactions.length ?? 0));

        await useStore.getState().fillTransactions();
        unsub();

        // one write per chunk, not a single coalesced write at the end
        expect(writes.filter((n) => n > 0)).toEqual([TX_CHUNK, TX_CHUNK * 2]);
    });

    it("stops once the loaded rows reach the total on a full page", async () => {
        const rows = ledger(TX_CHUNK);
        const transactions = vi
            .spyOn(api, "transactions")
            .mockImplementation(async ({ limit = TX_CHUNK, offset = 0 } = {}) => ({
                total: TX_CHUNK,
                rows: rows.slice(offset, offset + limit),
            }));
        useStore.setState({
            snapshot: buildSnapshot({ transactions: [], transactionsTotal: TX_CHUNK }),
            loading: false,
        });

        await useStore.getState().fillTransactions();

        // exactly-equal counts as done: a second page is never requested
        expect(transactions).toHaveBeenCalledTimes(1);
        expect(useStore.getState().snapshot!.transactions).toHaveLength(TX_CHUNK);
        expect(useStore.getState().txProgress).toBeNull();
    });
});
