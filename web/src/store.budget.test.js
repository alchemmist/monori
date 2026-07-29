import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { useStore } from "./store.js";

beforeEach(() => {
    useStore.setState({
        snapshot: {
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
        },
        toast: null,
    });
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("fillBudgetForward", () => {
    it("persists one category's amount into every later month of the year", async () => {
        vi.spyOn(api, "bulkBudgets").mockResolvedValue({ set: 9 });

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
                .snapshot.budgets.filter((b) => b.categoryId === 7 && b.year === 2027)
                .sort((a, b) => a.month - b.month),
        ).toEqual([{ categoryId: 7, year: 2027, month: 3, amount: 25_000 }, ...cells]);
        expect(useStore.getState().snapshot.budgets).toContainEqual({
            categoryId: 8,
            year: 2027,
            month: 4,
            amount: 5_000,
        });
    });

    it("clears later months when the selected source amount is zero", async () => {
        vi.spyOn(api, "bulkBudgets").mockResolvedValue({ set: 9 });

        useStore.setState((state) => ({
            snapshot: {
                ...state.snapshot,
                budgets: state.snapshot.budgets.filter(
                    (b) => !(b.categoryId === 7 && b.year === 2027 && b.month === 3),
                ),
            },
        }));

        await useStore.getState().fillBudgetForward(7, 2027, 3);

        expect(
            useStore
                .getState()
                .snapshot.budgets.filter((b) => b.categoryId === 7 && b.year === 2027),
        ).toEqual([]);
    });
});

describe("copyBudgetYear", () => {
    it("waits for pending budget edits before copying persisted values", async () => {
        let finishWrite;
        const pendingWrite = new Promise((resolve) => {
            finishWrite = resolve;
        });
        vi.spyOn(api, "putBudget").mockReturnValue(pendingWrite);
        vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });

        const write = useStore.getState().setBudget(7, 2027, 3, 30_000);
        const copy = useStore.getState().copyBudgetYear(2027, 2028);
        await Promise.resolve();

        expect(api.copyBudgetYear).not.toHaveBeenCalled();
        finishWrite();
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

    it("does not hide an earlier failed edit behind a later successful edit", async () => {
        let rejectFirst;
        const firstWrite = new Promise((_, reject) => {
            rejectFirst = reject;
        });
        vi.spyOn(api, "putBudget").mockReturnValueOnce(firstWrite).mockResolvedValueOnce(undefined);
        vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 0, budgets: [] });

        const failed = useStore.getState().setBudget(7, 2027, 3, 30_000);
        const succeeded = useStore.getState().setBudget(7, 2027, 4, 20_000);
        const copy = useStore.getState().copyBudgetYear(2027, 2028);
        rejectFirst(new Error("save failed"));

        await expect(failed).rejects.toThrow("save failed");
        await succeeded;
        await expect(copy).rejects.toThrow("save failed");
        expect(api.copyBudgetYear).not.toHaveBeenCalled();
    });

    it("preserves an edit made after copying started", async () => {
        let finishCopy;
        vi.spyOn(api, "copyBudgetYear").mockReturnValue(
            new Promise((resolve) => {
                finishCopy = resolve;
            }),
        );
        vi.spyOn(api, "putBudget").mockResolvedValue(undefined);

        const copy = useStore.getState().copyBudgetYear(2027, 2028);
        await vi.waitFor(() => expect(api.copyBudgetYear).toHaveBeenCalled());
        const edit = useStore.getState().setBudget(7, 2028, 3, 42_000);
        finishCopy({
            copied: 1,
            budgets: [{ categoryId: 7, year: 2028, month: 3, amount: 25_000 }],
        });

        await copy;
        await edit;
        expect(useStore.getState().snapshot.budgets).toContainEqual({
            categoryId: 7,
            year: 2028,
            month: 3,
            amount: 42_000,
        });
    });

    it("replaces the target year with an exact copy of the source year", async () => {
        const persisted = [
            { categoryId: 7, year: 2028, month: 3, amount: 25_000 },
            { categoryId: 7, year: 2028, month: 4, amount: 9_000 },
        ];
        vi.spyOn(api, "copyBudgetYear").mockResolvedValue({ copied: 2, budgets: persisted });
        useStore.setState((state) => ({
            snapshot: {
                ...state.snapshot,
                budgets: [
                    ...state.snapshot.budgets,
                    { categoryId: 7, year: 2028, month: 1, amount: 999 },
                ],
            },
        }));

        const count = await useStore.getState().copyBudgetYear(2027, 2028);

        expect(count).toBe(2);
        expect(api.copyBudgetYear).toHaveBeenCalledWith(2027, 2028);
        expect(useStore.getState().snapshot.budgets.filter((b) => b.year === 2028)).toEqual(
            persisted,
        );
        expect(useStore.getState().snapshot.budgets.filter((b) => b.year === 2027)).toHaveLength(3);
    });

    it("keeps the local budget unchanged when persistence fails", async () => {
        vi.spyOn(api, "copyBudgetYear").mockRejectedValue(new Error("offline"));
        const before = useStore.getState().snapshot.budgets;

        await expect(useStore.getState().copyBudgetYear(2027, 2028)).rejects.toThrow("offline");

        expect(useStore.getState().snapshot.budgets).toBe(before);
    });
});
