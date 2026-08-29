import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { useStore } from "./store.js";
import { buildSnapshot, tx as makeTx } from "./test/render.js";
import type { Snapshot, Transaction } from "./types.js";

const tx = (id: number, date = "2026-01-05T00:00:00"): Transaction =>
    makeTx(id, {
        date,
        amount: -100 * id,
        description: `tx ${id}`,
        hidden: false,
    });

const flush = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
    useStore.setState({
        snapshot: buildSnapshot({
            accounts: [],
            groups: [],
            categories: [],
            budgets: [],
            connections: [],
            transactions: [tx(1, "2026-01-01T00:00:00"), tx(2), tx(3, "2026-02-01T00:00:00")],
            transactionsTotal: 3,
        }),
        hiddenTx: null,
        toast: null,
    });
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("hiding transactions", () => {
    it("hideTx moves the row out of the snapshot and patches the server", async () => {
        vi.spyOn(api, "patchTx").mockResolvedValue({});

        useStore.getState().hideTx(2);

        const s = useStore.getState();
        expect(s.snapshot!.transactions.map((t) => t.id)).toEqual([1, 3]);
        expect(s.snapshot!.transactionsTotal).toBe(2);
        expect(s.hiddenTx!.map((t) => t.id)).toEqual([2]);
        expect(s.hiddenTx![0]!.hidden).toBe(true);
        await flush();
        expect(api.patchTx).toHaveBeenCalledWith(2, { hidden: true });
    });

    it("unhideTx puts the row back in canonical date order", async () => {
        vi.spyOn(api, "patchTx").mockResolvedValue({});

        useStore.getState().hideTx(2);
        useStore.getState().unhideTx(2);

        const s = useStore.getState();
        expect(s.snapshot!.transactions.map((t) => t.id)).toEqual([1, 2, 3]);
        expect(s.snapshot!.transactions[1]!.hidden).toBe(false);
        expect(s.snapshot!.transactionsTotal).toBe(3);
        expect(s.hiddenTx).toEqual([]);
        await flush();
        expect(api.patchTx).toHaveBeenLastCalledWith(2, { hidden: false });
    });

    it("a rapid hide then unhide reaches the server in that order", async () => {
        const calls: Array<boolean | undefined> = [];
        let releaseFirst: (value: { ok?: boolean }) => void = () => undefined;
        vi.spyOn(api, "patchTx").mockImplementation((_id, patch) => {
            calls.push(patch.hidden);
            if (calls.length === 1) return new Promise((r) => (releaseFirst = r));
            return Promise.resolve({});
        });

        useStore.getState().hideTx(2);
        useStore.getState().unhideTx(2);
        await flush();

        // the unhide PATCH waits behind the unresolved hide PATCH
        expect(calls).toEqual([true]);
        releaseFirst({});
        await flush();
        expect(calls).toEqual([true, false]);
    });

    it("hiding an unknown id is a no-op", async () => {
        const patch = vi.spyOn(api, "patchTx").mockResolvedValue({});

        useStore.getState().hideTx(99);
        useStore.getState().unhideTx(99);
        await flush();

        expect(useStore.getState().snapshot!.transactions).toHaveLength(3);
        expect(patch).not.toHaveBeenCalled();
    });

    it("loadHiddenTx replaces the local list with the server truth", async () => {
        vi.spyOn(api, "hiddenTx").mockResolvedValue({
            total: 1,
            rows: [{ ...tx(9), hidden: true }],
        });

        await useStore.getState().loadHiddenTx();

        expect(useStore.getState().hiddenTx!.map((t) => t.id)).toEqual([9]);
    });

    it("loadHiddenTx pages through more rows than one request returns", async () => {
        const spy = vi
            .spyOn(api, "hiddenTx")
            .mockResolvedValueOnce({ total: 2, rows: [{ ...tx(9), hidden: true }] })
            .mockResolvedValueOnce({
                total: 2,
                rows: [{ ...tx(8, "2026-03-01T00:00:00"), hidden: true }],
            });

        await useStore.getState().loadHiddenTx();

        expect(spy).toHaveBeenNthCalledWith(1, 0);
        expect(spy).toHaveBeenNthCalledWith(2, 1);
        expect(useStore.getState().hiddenTx!.map((t) => t.id)).toEqual([9, 8]);
    });

    it("a stale hidden-list response cannot overwrite a newer hide", async () => {
        vi.spyOn(api, "patchTx").mockResolvedValue({});
        let releaseLoad: (value: { total: number; rows: Transaction[] }) => void;
        vi.spyOn(api, "hiddenTx").mockReturnValue(new Promise((r) => (releaseLoad = r)));

        const loading = useStore.getState().loadHiddenTx();
        useStore.getState().hideTx(2);
        releaseLoad!({ total: 0, rows: [] });
        await loading;

        expect(useStore.getState().hiddenTx!.map((t) => t.id)).toEqual([2]);
    });

    it("logout clears the hidden list", () => {
        vi.stubGlobal("localStorage", { removeItem: () => {} });
        useStore.setState({ hiddenTx: [{ ...tx(9), hidden: true }] });

        useStore.getState().logout();

        expect(useStore.getState().hiddenTx).toBeNull();
        vi.unstubAllGlobals();
    });

    it("load clears hidden rows before replacing the snapshot", async () => {
        let resolveSnapshot: (value: Snapshot) => void;
        vi.spyOn(api, "snapshot").mockReturnValue(
            new Promise((resolve) => {
                resolveSnapshot = resolve;
            }),
        );
        vi.spyOn(api, "hiddenTx").mockResolvedValue({ total: 0, rows: [] });
        useStore.setState({ hiddenTx: [{ ...tx(9), hidden: true }] });

        const loading = useStore.getState().load();
        expect(useStore.getState().hiddenTx).toBeNull();

        resolveSnapshot!({ ...useStore.getState().snapshot!, transactionsTotal: 3 });
        await loading;
    });

    it("a failed hide patch surfaces a toast", async () => {
        vi.spyOn(api, "patchTx").mockRejectedValue(new Error("network down"));

        useStore.getState().hideTx(2);
        await vi.waitFor(() => expect(useStore.getState().toast).toBeTruthy());

        expect(useStore.getState().toast!.title).toMatch(/hide/i);
        expect(useStore.getState().snapshot!.transactions.map((row) => row.id)).toEqual([1, 2, 3]);
        expect(useStore.getState().hiddenTx).toEqual([]);
    });

    it("rolls back a failed hide after hiding another transaction", async () => {
        let rejectFirst: (reason?: unknown) => void;
        vi.spyOn(api, "patchTx")
            .mockReturnValueOnce(
                new Promise((_, reject) => {
                    rejectFirst = reject;
                }),
            )
            .mockResolvedValueOnce({});

        useStore.getState().hideTx(1);
        useStore.getState().hideTx(2);
        await vi.waitFor(() => expect(api.patchTx).toHaveBeenCalledTimes(2));
        rejectFirst!(new Error("network down"));

        await vi.waitFor(() =>
            expect(useStore.getState().snapshot!.transactions.map((row) => row.id)).toEqual([1, 3]),
        );
        expect(useStore.getState().hiddenTx!.map((row) => row.id)).toEqual([2]);
    });

    it("rolls back a failed unhide after unhiding another transaction", async () => {
        let rejectFirst: (reason?: unknown) => void;
        vi.spyOn(api, "patchTx")
            .mockReturnValueOnce(
                new Promise((_, reject) => {
                    rejectFirst = reject;
                }),
            )
            .mockResolvedValueOnce({});
        useStore.setState({
            snapshot: buildSnapshot({
                transactions: [tx(3, "2026-02-01T00:00:00")],
                transactionsTotal: 1,
            }),
            hiddenTx: [
                { ...tx(1, "2026-01-01T00:00:00"), hidden: true },
                { ...tx(2), hidden: true },
            ],
        });

        useStore.getState().unhideTx(1);
        useStore.getState().unhideTx(2);
        await vi.waitFor(() => expect(api.patchTx).toHaveBeenCalledTimes(2));
        rejectFirst!(new Error("network down"));

        await vi.waitFor(() =>
            expect(useStore.getState().snapshot!.transactions.map((row) => row.id)).toEqual([2, 3]),
        );
        expect(useStore.getState().hiddenTx!.map((row) => row.id)).toEqual([1]);
    });
});
