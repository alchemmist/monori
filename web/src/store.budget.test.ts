import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { resetStoreForTests, useStore } from "./store.js";
import { buildSnapshot } from "./test/render.js";

beforeEach(() => {
    resetStoreForTests();
    useStore.setState({
        snapshot: buildSnapshot({
            accounts: [],
            groups: [],
            categories: [{ id: 7, name: "Groceries" }],
            budgets: [
                { categoryId: 7, year: 2027, month: 3, amount: 25_000 },
                { categoryId: 7, year: 2027, month: 4, amount: 10_000 },
                { categoryId: 8, year: 2027, month: 4, amount: 5_000 },
            ],
            connections: [],
            transactions: [],
            transactionsTotal: 0,
        }),
        toast: null,
    });
});

afterEach(() => {
    window.history.replaceState({}, "", "/");
    localStorage.removeItem("monori_token");
    vi.restoreAllMocks();
});

describe("fillBudgetForward", () => {
    it("persists one category's amount into every later month of the year", async () => {
        vi.spyOn(api, "bulkBudgets").mockResolvedValue({ set: 9 });
        useStore.setState((state) => ({
            snapshot: {
                ...state.snapshot!,
                budgets: [
                    { categoryId: 8, year: 2027, month: 3, amount: 999 },
                    { categoryId: 7, year: 2026, month: 3, amount: 777 },
                    { categoryId: 7, year: 2026, month: 4, amount: 888 },
                    ...state.snapshot!.budgets,
                ],
            },
        }));

        const count = await useStore.getState().fillBudgetForward(7, 2027, 3);

        const cells = Array.from({ length: 9 }, (_, i) => ({
            categoryId: 7,
            year: 2027,
            month: i + 4,
            amount: 25_000,
        }));
        expect(count).toBe(9);
        expect(api.bulkBudgets).toHaveBeenCalledWith(cells);
        expect(
            useStore
                .getState()
                .snapshot!.budgets.filter((b) => b.categoryId === 7 && b.year === 2027)
                .sort((a, b) => a.month - b.month),
        ).toEqual([{ categoryId: 7, year: 2027, month: 3, amount: 25_000 }, ...cells]);
        expect(useStore.getState().snapshot!.budgets).toContainEqual({
            categoryId: 8,
            year: 2027,
            month: 4,
            amount: 5_000,
        });
        expect(useStore.getState().snapshot!.budgets).toContainEqual({
            categoryId: 7,
            year: 2026,
            month: 4,
            amount: 888,
        });
    });

    it("clears later months when the selected source amount is zero", async () => {
        vi.spyOn(api, "bulkBudgets").mockResolvedValue({ set: 9 });

        useStore.setState((state) => ({
            snapshot: {
                ...state.snapshot!,
                budgets: state.snapshot!.budgets.filter(
                    (b) => !(b.categoryId === 7 && b.year === 2027 && b.month === 3),
                ),
            },
        }));

        await useStore.getState().fillBudgetForward(7, 2027, 3);

        expect(
            useStore
                .getState()
                .snapshot!.budgets.filter((b) => b.categoryId === 7 && b.year === 2027),
        ).toEqual([]);
    });

    it("does nothing after December", async () => {
        const bulk = vi.spyOn(api, "bulkBudgets");

        await expect(useStore.getState().fillBudgetForward(7, 2027, 12)).resolves.toBe(0);

        expect(bulk).not.toHaveBeenCalled();
    });

    it("fills the demo locally without calling the API", async () => {
        window.history.replaceState({}, "", "/demo");
        const bulk = vi.spyOn(api, "bulkBudgets");

        await expect(useStore.getState().fillBudgetForward(7, 2027, 3)).resolves.toBe(9);

        expect(bulk).not.toHaveBeenCalled();
    });
});

describe("setBudgets", () => {
    it("skips an empty cell set", async () => {
        const bulk = vi.spyOn(api, "bulkBudgets");
        const before = useStore.getState().snapshot!.budgets;

        await useStore.getState().setBudgets([]);

        expect(bulk).not.toHaveBeenCalled();
        expect(useStore.getState().snapshot!.budgets).toBe(before);
    });

    it("persists and replaces only the exact cells", async () => {
        const bulk = vi.spyOn(api, "bulkBudgets").mockResolvedValue({ set: 2 });
        const cells = [
            { categoryId: 7, year: 2027, month: 3, amount: 40_000 },
            { categoryId: 7, year: 2027, month: 4, amount: 0 },
        ];

        await useStore.getState().setBudgets(cells);

        expect(bulk).toHaveBeenCalledExactlyOnceWith(cells);
        expect(useStore.getState().snapshot!.budgets).toEqual([
            { categoryId: 8, year: 2027, month: 4, amount: 5_000 },
            { categoryId: 7, year: 2027, month: 3, amount: 40_000 },
        ]);
    });

    it("updates the demo locally without calling the API", async () => {
        window.history.replaceState({}, "", "/demo");
        const bulk = vi.spyOn(api, "bulkBudgets");

        await useStore
            .getState()
            .setBudgets([{ categoryId: 7, year: 2027, month: 3, amount: 40_000 }]);

        expect(bulk).not.toHaveBeenCalled();
        expect(useStore.getState().snapshot!.budgets).toContainEqual({
            categoryId: 7,
            year: 2027,
            month: 3,
            amount: 40_000,
        });
    });
});

describe("copyBudgetYear", () => {
    it("records a successful zero budget as an empty baseline", async () => {
        vi.spyOn(api, "putBudget").mockResolvedValue({ ok: true });

        await useStore.getState().setBudget(7, 2027, 3, 0);

        expect(useStore.getState().snapshot!.budgets).not.toContainEqual(
            expect.objectContaining({ categoryId: 7, year: 2027, month: 3 }),
        );
    });

    it("does not let a stale write clear a new session's budget baseline", async () => {
        let finishOldWrite: ((result: { ok: boolean }) => void) | undefined;
        let failNewWrite: ((error: Error) => void) | undefined;
        vi.spyOn(api, "putBudget")
            .mockReturnValueOnce(
                new Promise((resolve) => {
                    finishOldWrite = resolve;
                }),
            )
            .mockReturnValueOnce(
                new Promise((_resolve, reject) => {
                    failNewWrite = reject;
                }),
            );

        const oldWrite = useStore.getState().setBudget(7, 2027, 3, 30_000);
        await vi.waitFor(() => expect(api.putBudget).toHaveBeenCalledOnce());
        resetStoreForTests();
        useStore.setState({
            snapshot: buildSnapshot({
                categories: [{ id: 7, name: "Groceries" }],
                budgets: [{ categoryId: 7, year: 2027, month: 3, amount: 10_000 }],
            }),
        });

        const newWrite = useStore.getState().setBudget(7, 2027, 3, 20_000);
        await vi.waitFor(() => expect(api.putBudget).toHaveBeenCalledTimes(2));
        finishOldWrite?.({ ok: true });
        await expect(oldWrite).rejects.toThrow("session changed");
        failNewWrite?.(new Error("new write failed"));
        await expect(newWrite).rejects.toThrow("new write failed");
        expect(useStore.getState().snapshot!.budgets).toContainEqual({
            categoryId: 7,
            year: 2027,
            month: 3,
            amount: 10_000,
        });
    });

    it("discards queued budget operations when the authenticated session changes", async () => {
        let finishWrite: ((result: { ok: boolean }) => void) | undefined;
        const pendingWrite = new Promise<{ ok: boolean }>((resolve) => {
            finishWrite = resolve;
        });
        const put = vi
            .spyOn(api, "putBudget")
            .mockReturnValueOnce(pendingWrite)
            .mockResolvedValueOnce({ ok: true });
        const copy = vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });
        localStorage.setItem("monori_token", "user-a");

        const running = useStore.getState().setBudget(7, 2027, 3, 30_000);
        await vi.waitFor(() => expect(put).toHaveBeenCalledTimes(1));
        const queued = useStore.getState().setBudget(7, 2027, 4, 20_000);
        useStore.getState().logout();
        localStorage.setItem("monori_token", "user-b");
        finishWrite?.({ ok: true });

        await expect(running).rejects.toThrow("session changed");
        await expect(queued).rejects.toThrow("session changed");
        expect(put).toHaveBeenCalledTimes(1);
        await expect(useStore.getState().copyBudgetYear(2027, 2028)).resolves.toBe(0);
        expect(copy).toHaveBeenCalledExactlyOnceWith(2027, 2028);
        expect(useStore.getState().toast).toBeNull();
    });

    it("discards queued writes when the token changes outside the store", async () => {
        let finishWrite: ((result: { ok: boolean }) => void) | undefined;
        const put = vi.spyOn(api, "putBudget").mockReturnValue(
            new Promise((resolve) => {
                finishWrite = resolve;
            }),
        );
        localStorage.setItem("monori_token", "user-a");

        const running = useStore.getState().setBudget(7, 2027, 3, 30_000);
        await vi.waitFor(() => expect(put).toHaveBeenCalledTimes(1));
        const queued = useStore.getState().setBudget(7, 2027, 4, 20_000);
        localStorage.setItem("monori_token", "user-b");
        finishWrite?.({ ok: true });

        await expect(running).rejects.toThrow("session changed");
        await expect(queued).rejects.toThrow("session changed");
        expect(put).toHaveBeenCalledTimes(1);
    });

    it("invalidates queued writes when auth is checked without a token", async () => {
        let finishWrite: ((result: { ok: boolean }) => void) | undefined;
        const put = vi.spyOn(api, "putBudget").mockReturnValue(
            new Promise((resolve) => {
                finishWrite = resolve;
            }),
        );

        const running = useStore.getState().setBudget(7, 2027, 3, 30_000);
        await vi.waitFor(() => expect(put).toHaveBeenCalledTimes(1));
        const queued = useStore.getState().setBudget(7, 2027, 4, 20_000);
        await useStore.getState().checkAuth();
        finishWrite?.({ ok: true });

        await expect(running).rejects.toThrow("session changed");
        await expect(queued).rejects.toThrow("session changed");
        expect(put).toHaveBeenCalledTimes(1);
    });

    it("clears failed budget state after rejected authentication", async () => {
        vi.spyOn(api, "putBudget").mockRejectedValue(new Error("save failed"));
        vi.spyOn(api, "authMe").mockRejectedValue(new Error("expired"));
        const copy = vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });
        localStorage.setItem("monori_token", "expired");

        await expect(useStore.getState().setBudget(7, 2027, 3, 30_000)).rejects.toThrow(
            "save failed",
        );
        await useStore.getState().checkAuth();

        await expect(useStore.getState().copyBudgetYear(2027, 2028)).resolves.toBe(0);
        expect(copy).toHaveBeenCalledOnce();
    });

    it("clears failed budget state after login", async () => {
        vi.spyOn(api, "putBudget").mockRejectedValue(new Error("save failed"));
        vi.spyOn(api, "authLogin").mockResolvedValue({ access_token: "new-token" });
        vi.spyOn(api, "authMe").mockResolvedValue({ id: 2, email: "new@example.test" });
        const copy = vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });
        localStorage.setItem("monori_token", "old-token");

        await expect(useStore.getState().setBudget(7, 2027, 3, 30_000)).rejects.toThrow(
            "save failed",
        );
        await useStore.getState().login("new@example.test", "password");

        await expect(useStore.getState().copyBudgetYear(2027, 2028)).resolves.toBe(0);
        expect(copy).toHaveBeenCalledOnce();
    });

    it("invalidates queued writes on logout even if the token value is restored", async () => {
        let finishWrite: ((result: { ok: boolean }) => void) | undefined;
        const put = vi.spyOn(api, "putBudget").mockReturnValue(
            new Promise((resolve) => {
                finishWrite = resolve;
            }),
        );
        localStorage.setItem("monori_token", "same-token");

        const running = useStore.getState().setBudget(7, 2027, 3, 30_000);
        await vi.waitFor(() => expect(put).toHaveBeenCalledTimes(1));
        const queued = useStore.getState().setBudget(7, 2027, 4, 20_000);
        useStore.getState().logout();
        localStorage.setItem("monori_token", "same-token");
        finishWrite?.({ ok: true });

        await expect(running).rejects.toThrow("session changed");
        await expect(queued).rejects.toThrow("session changed");
        expect(put).toHaveBeenCalledTimes(1);
    });

    it("does not retain a stale write failure after auth changes", async () => {
        let rejectWrite: ((error: Error) => void) | undefined;
        vi.spyOn(api, "putBudget").mockReturnValue(
            new Promise((_, reject) => {
                rejectWrite = reject;
            }),
        );
        vi.spyOn(api, "authMe").mockResolvedValue({ id: 1, email: "a@b.c" });
        const copy = vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });
        localStorage.setItem("monori_token", "same-token");

        const running = useStore.getState().setBudget(7, 2027, 3, 30_000);
        await vi.waitFor(() => expect(api.putBudget).toHaveBeenCalledOnce());
        await useStore.getState().checkAuth();
        rejectWrite?.(new Error("old failure"));

        await expect(running).rejects.toThrow("old failure");
        await expect(useStore.getState().copyBudgetYear(2027, 2028)).resolves.toBe(0);
        expect(copy).toHaveBeenCalledOnce();
    });

    it("invalidates queued writes when auth is refreshed with the same token", async () => {
        let finishWrite: ((result: { ok: boolean }) => void) | undefined;
        const put = vi.spyOn(api, "putBudget").mockReturnValue(
            new Promise((resolve) => {
                finishWrite = resolve;
            }),
        );
        vi.spyOn(api, "authMe").mockResolvedValue({ id: 1, email: "a@b.c" });
        localStorage.setItem("monori_token", "same-token");

        const running = useStore.getState().setBudget(7, 2027, 3, 30_000);
        await vi.waitFor(() => expect(put).toHaveBeenCalledTimes(1));
        const queued = useStore.getState().setBudget(7, 2027, 4, 20_000);
        await useStore.getState().checkAuth();
        finishWrite?.({ ok: true });

        await expect(running).rejects.toThrow("session changed");
        await expect(queued).rejects.toThrow("session changed");
        expect(put).toHaveBeenCalledTimes(1);
    });

    it("clears failed writes and revisions after auth refresh", async () => {
        vi.spyOn(api, "putBudget").mockRejectedValue(new Error("save failed"));
        vi.spyOn(api, "authMe").mockResolvedValue({ id: 1, email: "a@b.c" });
        const persisted = [{ categoryId: 7, year: 2028, month: 3, amount: 25_000 }];
        const copy = vi
            .spyOn(api, "copyBudgetYear")
            .mockResolvedValue({ copied: 1, budgets: persisted });
        localStorage.setItem("monori_token", "same-token");

        await expect(useStore.getState().setBudget(7, 2028, 3, 30_000)).rejects.toThrow(
            "save failed",
        );
        await useStore.getState().checkAuth();

        await expect(useStore.getState().copyBudgetYear(2027, 2028)).resolves.toBe(1);
        expect(copy).toHaveBeenCalledExactlyOnceWith(2027, 2028);
        expect(useStore.getState().snapshot!.budgets.filter((b) => b.year === 2028)).toEqual(
            persisted,
        );
    });

    it("copies a budget year locally in the demo without calling the API", async () => {
        window.history.replaceState({}, "", "/demo");
        const copy = vi.spyOn(api, "copyBudgetYear");
        useStore.setState((state) => ({
            snapshot: {
                ...state.snapshot!,
                budgets: [
                    ...state.snapshot!.budgets,
                    { categoryId: 7, year: 2026, month: 1, amount: 999 },
                ],
            },
        }));

        const count = await useStore.getState().copyBudgetYear(2027, 2028);

        expect(count).toBe(3);
        expect(copy).not.toHaveBeenCalled();
        expect(useStore.getState().snapshot!.budgets.filter((b) => b.year === 2028)).toEqual([
            { categoryId: 7, year: 2028, month: 3, amount: 25_000 },
            { categoryId: 7, year: 2028, month: 4, amount: 10_000 },
            { categoryId: 8, year: 2028, month: 4, amount: 5_000 },
        ]);
    });

    it("waits for pending budget edits before copying persisted values", async () => {
        let finishWrite: ((result: { ok: boolean }) => void) | undefined;
        const pendingWrite = new Promise<{ ok: boolean }>((resolve) => {
            finishWrite = resolve;
        });
        vi.spyOn(api, "putBudget").mockReturnValue(pendingWrite);
        vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });

        const write = useStore.getState().setBudget(7, 2027, 3, 30_000);
        const copy = useStore.getState().copyBudgetYear(2027, 2028);
        await Promise.resolve();

        expect(api.copyBudgetYear).not.toHaveBeenCalled();
        finishWrite?.({ ok: true });
        await write;
        await copy;
        expect(api.copyBudgetYear).toHaveBeenCalledWith(2027, 2028);
    });

    it("does not copy when a pending budget edit failed", async () => {
        vi.spyOn(api, "putBudget").mockRejectedValue(new Error("save failed"));
        vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });

        const write = useStore.getState().setBudget(7, 2027, 3, 30_000);
        const copy = useStore.getState().copyBudgetYear(2027, 2028);

        await expect(write).rejects.toThrow("save failed");
        await expect(copy).rejects.toThrow("save failed");
        expect(api.copyBudgetYear).not.toHaveBeenCalled();
    });

    it("does not copy after a budget edit has already failed", async () => {
        vi.spyOn(api, "putBudget").mockRejectedValue(new Error("save failed"));
        vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });

        await expect(useStore.getState().setBudget(7, 2027, 3, 30_000)).rejects.toThrow(
            "save failed",
        );

        await expect(useStore.getState().copyBudgetYear(2027, 2028)).rejects.toThrow("save failed");
        expect(api.copyBudgetYear).not.toHaveBeenCalled();
    });

    it("allows copying after the failed budget cell is saved again", async () => {
        vi.spyOn(api, "putBudget")
            .mockRejectedValueOnce(new Error("save failed"))
            .mockResolvedValueOnce({ ok: true });
        vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });

        await expect(useStore.getState().setBudget(7, 2027, 3, 30_000)).rejects.toThrow(
            "save failed",
        );
        await useStore.getState().setBudget(7, 2027, 3, 30_000);
        await useStore.getState().copyBudgetYear(2027, 2028);

        expect(api.copyBudgetYear).toHaveBeenCalledWith(2027, 2028);
    });

    it("does not hide an earlier failed edit behind a later successful edit", async () => {
        let rejectFirst: ((error: Error) => void) | undefined;
        const firstWrite = new Promise<{ ok: boolean }>((_, reject) => {
            rejectFirst = reject;
        });
        vi.spyOn(api, "putBudget")
            .mockReturnValueOnce(firstWrite)
            .mockResolvedValueOnce({ ok: true });
        vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });

        const failed = useStore.getState().setBudget(7, 2027, 3, 30_000);
        const succeeded = useStore.getState().setBudget(7, 2027, 4, 20_000);
        const copy = useStore.getState().copyBudgetYear(2027, 2028);
        rejectFirst?.(new Error("save failed"));

        await expect(failed).rejects.toThrow("save failed");
        await succeeded;
        await expect(copy).rejects.toThrow("save failed");
        expect(api.copyBudgetYear).not.toHaveBeenCalled();
    });

    it("preserves an edit made after copying started", async () => {
        let finishCopy:
            | ((result: {
                  copied: number;
                  budgets: Array<{
                      categoryId: number;
                      year: number;
                      month: number;
                      amount: number;
                  }>;
              }) => void)
            | undefined;
        vi.spyOn(api, "copyBudgetYear").mockReturnValue(
            new Promise((resolve) => {
                finishCopy = resolve;
            }),
        );
        vi.spyOn(api, "putBudget").mockResolvedValue({ ok: true });

        const copy = useStore.getState().copyBudgetYear(2027, 2028);
        await vi.waitFor(() => expect(api.copyBudgetYear).toHaveBeenCalled());
        const edit = useStore.getState().setBudget(7, 2028, 3, 42_000);
        finishCopy?.({
            copied: 1,
            budgets: [{ categoryId: 7, year: 2028, month: 3, amount: 25_000 }],
        });

        await copy;
        await edit;
        expect(useStore.getState().snapshot!.budgets.filter((b) => b.year === 2028)).toEqual([
            { categoryId: 7, year: 2028, month: 3, amount: 42_000 },
        ]);
    });

    it("replaces the target year with an exact copy of the source year", async () => {
        const persisted = [
            { categoryId: 7, year: 2028, month: 3, amount: 25_000 },
            { categoryId: 7, year: 2028, month: 4, amount: 9_000 },
        ];
        vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 2, budgets: persisted });
        useStore.setState((state) => ({
            snapshot: {
                ...state.snapshot!,
                budgets: [
                    ...state.snapshot!.budgets,
                    { categoryId: 7, year: 2028, month: 1, amount: 999 },
                ],
            },
        }));

        const count = await useStore.getState().copyBudgetYear(2027, 2028);

        expect(count).toBe(2);
        expect(api.copyBudgetYear).toHaveBeenCalledWith(2027, 2028);
        expect(useStore.getState().snapshot!.budgets.filter((b) => b.year === 2028)).toEqual(
            persisted,
        );
        expect(useStore.getState().snapshot!.budgets.filter((b) => b.year === 2027)).toHaveLength(
            3,
        );
    });

    it("keeps the local budget unchanged when persistence fails", async () => {
        vi.spyOn(api, "copyBudgetYear").mockRejectedValue(new Error("offline"));
        const before = useStore.getState().snapshot!.budgets;

        await expect(useStore.getState().copyBudgetYear(2027, 2028)).rejects.toThrow("offline");

        expect(useStore.getState().snapshot!.budgets).toBe(before);
    });
});
