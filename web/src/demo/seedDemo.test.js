import { beforeEach, describe, expect, it, vi } from "vitest";
import { seedDemoData } from "./seedDemo.js";
import { demoSnapshot } from "./demoData.js";
import { api } from "../api.js";

vi.mock("../api.js", () => ({
    api: {
        snapshot: vi.fn(),
        patchAccount: vi.fn(),
        createAccount: vi.fn(),
        createGroup: vi.fn(),
        createCategory: vi.fn(),
        bulkBudgets: vi.fn(),
        importCommit: vi.fn(),
        transactions: vi.fn(),
        hiddenTx: vi.fn(),
        createTransfer: vi.fn(),
    },
}));

const emptySnapshot = () => ({ accounts: [], groups: [], categories: [] });

beforeEach(() => {
    vi.clearAllMocks();
    let nextId = 1000;
    api.createAccount.mockImplementation(async () => ({ id: nextId++ }));
    api.createGroup.mockImplementation(async () => ({ id: nextId++ }));
    api.createCategory.mockImplementation(async () => ({ id: nextId++ }));
    api.patchAccount.mockResolvedValue({});
    api.bulkBudgets.mockResolvedValue({});
    api.importCommit.mockResolvedValue({ inserted: 3, skipped: 1 });
    api.createTransfer.mockResolvedValue({ id: 1 });
    api.transactions.mockResolvedValue({ rows: [], total: 0 });
    api.hiddenTx.mockResolvedValue({ rows: [], total: 0 });
});

describe("seedDemoData on an empty account", () => {
    it("creates every account, group and category, then budgets and imports", async () => {
        api.snapshot.mockResolvedValue(emptySnapshot());

        const res = await seedDemoData();

        expect(api.snapshot).toHaveBeenCalledWith({ light: true });

        expect(api.createAccount).toHaveBeenCalledTimes(demoSnapshot.accounts.length);
        for (const a of demoSnapshot.accounts) {
            expect(api.createAccount).toHaveBeenCalledWith(
                expect.objectContaining({ name: a.name, bankRef: `monori-demo:${a.id}` }),
            );
        }

        expect(api.createGroup).toHaveBeenCalledTimes(demoSnapshot.groups.length);
        expect(api.createCategory).toHaveBeenCalledTimes(demoSnapshot.categories.length);
        expect(api.patchAccount).not.toHaveBeenCalled();

        expect(api.bulkBudgets).toHaveBeenCalledTimes(1);
        expect(api.bulkBudgets.mock.calls[0][0]).toHaveLength(demoSnapshot.budgets.length);

        expect(api.importCommit).toHaveBeenCalledTimes(demoSnapshot.accounts.length);

        expect(res.imported).toBe(3 * demoSnapshot.accounts.length);
        expect(res.skipped).toBe(1 * demoSnapshot.accounts.length);
        expect(res.transfers).toBeGreaterThan(0);
    });

    it("passes plausible transaction rows to importCommit", async () => {
        api.snapshot.mockResolvedValue(emptySnapshot());
        await seedDemoData();

        const [rows, accountId] = api.importCommit.mock.calls[0];
        expect(typeof accountId).toBe("number");
        expect(rows.length).toBeGreaterThan(0);
        for (const r of rows) {
            expect(r.date).toMatch(/T12:00:00$/);
            expect(typeof r.amount).toBe("number");
            expect(r).toHaveProperty("bank_category");
            expect(r).toHaveProperty("mcc");
        }
    });

    it("creates a transfer for every demo transfer pair", async () => {
        api.snapshot.mockResolvedValue(emptySnapshot());
        const pairs = new Set(
            demoSnapshot.transactions.filter((t) => t.transferId).map((t) => t.transferId),
        );

        const res = await seedDemoData();

        expect(api.createTransfer).toHaveBeenCalledTimes(pairs.size);
        expect(res.transfers).toBe(pairs.size);
        const body = api.createTransfer.mock.calls[0][0];
        expect(body.date).toMatch(/T12:00:00$/);
        expect(body).toHaveProperty("fromAccountId");
        expect(body).toHaveProperty("toAccountId");
    });
});

describe("seedDemoData resuming a partial run", () => {
    it("patches accounts already tagged with the demo bank ref instead of creating them", async () => {
        api.snapshot.mockResolvedValue({
            accounts: demoSnapshot.accounts.map((a) => ({
                id: 500 + a.id,
                name: a.name,
                bankRef: `monori-demo:${a.id}`,
            })),
            groups: [],
            categories: [],
        });

        await seedDemoData();

        expect(api.patchAccount).toHaveBeenCalledTimes(demoSnapshot.accounts.length);
        expect(api.createAccount).not.toHaveBeenCalled();
    });

    it("reuses existing groups and categories by name", async () => {
        api.snapshot.mockResolvedValue({
            accounts: [],
            groups: demoSnapshot.groups.map((g) => ({ id: 700 + g.id, name: g.name })),
            categories: demoSnapshot.categories.map((c) => ({ id: 800 + c.id, name: c.name })),
        });

        await seedDemoData();

        expect(api.createGroup).not.toHaveBeenCalled();
        expect(api.createCategory).not.toHaveBeenCalled();
    });

    it("gives a new demo account a unique name when the name already exists", async () => {
        // A pre-existing account with the same display name but no demo bankRef
        // forces the unique-name branch.
        api.snapshot.mockResolvedValue({
            accounts: demoSnapshot.accounts.map((a) => ({
                id: 900 + a.id,
                name: a.name,
                bankRef: null,
            })),
            groups: [],
            categories: [],
        });

        await seedDemoData();

        expect(api.createAccount).toHaveBeenCalledTimes(demoSnapshot.accounts.length);
        for (const call of api.createAccount.mock.calls) {
            expect(call[0].name).toMatch(/\(Demo \d+\)$/);
        }
    });

    it("does not recreate a transfer whose pair is already present", async () => {
        api.snapshot.mockResolvedValue(emptySnapshot());
        // createAccount returns ids matching the demo account id for easy mapping.
        api.createAccount.mockImplementation(async ({ bankRef }) => {
            const demoId = Number(bankRef.split(":")[1]);
            return { id: demoId };
        });

        const pairs = new Map();
        for (const t of demoSnapshot.transactions) {
            if (!t.transferId) continue;
            const p = pairs.get(t.transferId) ?? {};
            p[t.amount < 0 ? "out" : "inn"] = t;
            pairs.set(t.transferId, p);
        }
        const existingRows = [];
        for (const { out, inn } of pairs.values()) {
            existingRows.push(
                {
                    transferId: out.transferId,
                    accountId: out.accountId,
                    amount: -inn.amount,
                    date: `${out.date}T00:00:00`,
                    comment: out.comment ?? "",
                },
                {
                    transferId: out.transferId,
                    accountId: inn.accountId,
                    amount: inn.amount,
                    date: `${inn.date}T00:00:00`,
                    comment: inn.comment ?? "",
                },
            );
        }
        api.transactions.mockResolvedValue({ rows: existingRows, total: existingRows.length });
        api.hiddenTx.mockResolvedValue({ rows: [], total: 0 });

        const res = await seedDemoData();

        expect(api.createTransfer).not.toHaveBeenCalled();
        expect(res.transfers).toBe(0);
    });

    it("pages through visible and hidden transactions", async () => {
        api.snapshot.mockResolvedValue(emptySnapshot());
        api.transactions
            .mockResolvedValueOnce({ rows: [{ id: 1 }, { id: 2 }], total: 3 })
            .mockResolvedValueOnce({ rows: [{ id: 3 }], total: 3 });
        api.hiddenTx.mockResolvedValueOnce({ rows: [{ id: 4 }], total: 1 });

        await seedDemoData();

        expect(api.transactions).toHaveBeenCalledWith({ limit: 1000, offset: 0 });
        expect(api.transactions).toHaveBeenCalledWith({ limit: 1000, offset: 2 });
        expect(api.hiddenTx).toHaveBeenCalledWith(0);
    });
});
