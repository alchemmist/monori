import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";

const ok = (body = {}) => ({ ok: true, json: vi.fn().mockResolvedValue(body), blob: vi.fn().mockResolvedValue(new Blob(["x"])) });

describe("api", () => {
    let fetch;
    beforeEach(() => {
        const values = new Map();
        vi.stubGlobal("localStorage", { getItem: (k) => values.get(k) ?? null, setItem: (k, v) => values.set(k, v), removeItem: (k) => values.delete(k), clear: () => values.clear() });
        fetch = vi.fn().mockResolvedValue(ok({ id: 7, transferId: "t" }));
        vi.stubGlobal("fetch", fetch);
    });

    it("adds auth headers and serializes each JSON endpoint", async () => {
        localStorage.setItem("monori_token", "secret");
        await api.snapshot({ light: true, limit: 5 }); await api.transactions({ limit: 2, offset: 3 });
        await api.putBudget({ categoryId: 1 }); await api.patchTx(1, { categoryId: 2 }); await api.deleteTx(1);
        await api.createAccount({ name: "Card" }); await api.patchAccount(1, { name: "Cash" }); await api.deleteAccount(1, 2); await api.reorderAccounts([2, 1]); await api.reconcileAccount(1, 50);
        await api.createTransfer({ amount: 10 }); await api.deleteTransfer("t");
        await api.createCategory({ name: "Food" }); await api.patchCategory(1, { name: "Home" }); await api.deleteCategory(1); await api.mergeCategory(1, 2); await api.reorderCategories([1]);
        await api.createGroup({ name: "Living" }); await api.patchGroup(1, { name: "Home" }); await api.deleteGroup(1); await api.reorderGroups([1]);
        await api.importPreview("rows", 1); await api.importCommit([], 1);
        await api.connectionsAvailable(); await api.createConnection({ provider: "bank" }); await api.deleteConnection(1); await api.syncConnection(1); await api.submitConnectionSms(1, "1234"); await api.cancelConnectionSync(1);
        await api.authRegister("a@b.c", "password"); await api.authLogin("a@b.c", "password"); await api.authMe("other");
        await api.adminOverview(); await api.adminUsers(); await api.adminUserDetail(1); await api.adminUserTransactions(1, { limit: 2, offset: 3 }); await api.adminDeleteUserTransactions(1, [2]); await api.adminActivity(); await api.adminSql("select 1", true, true); await api.adminDeleteUser(1);
        expect(fetch).toHaveBeenCalledWith("/api/snapshot?light=1&limit=5", expect.objectContaining({ headers: { Authorization: "Bearer secret" } }));
        expect(fetch).toHaveBeenCalledWith("/api/accounts/1?reassignTo=2", expect.objectContaining({ method: "DELETE" }));
        expect(fetch).toHaveBeenCalledWith("/api/auth/token", expect.objectContaining({ body: expect.any(URLSearchParams) }));
        expect(fetch).toHaveBeenCalledTimes(40);
    });

    it("uses defaults, handles multipart payloads and downloads exports", async () => {
        await api.snapshot(); await api.transactions(); await api.deleteAccount(1); await api.workbookPreview(new File(["x"], "book.xlsx")); await api.workbookCommit(new File(["x"], "book.xlsx"), { card: 1 }, "skip");
        const blob = await api.exportXlsx();
        expect(blob).toBeInstanceOf(Blob);
        expect(fetch).toHaveBeenCalledWith("/api/snapshot", expect.any(Object));
        expect(fetch).toHaveBeenCalledWith("/api/transactions?limit=1000&offset=0", expect.any(Object));
        expect(fetch).toHaveBeenCalledWith("/api/accounts/1", expect.objectContaining({ method: "DELETE" }));
        expect(fetch.mock.calls[3][1].body).toBeInstanceOf(FormData);
    });

    it("turns response details into errors and expires an unauthorized session", async () => {
        fetch.mockResolvedValueOnce({ ok: false, status: 400, statusText: "Bad", url: "/api/x", json: vi.fn().mockResolvedValue({ detail: "Bad input" }) });
        await expect(api.snapshot()).rejects.toThrow("Bad input");
        localStorage.setItem("monori_token", "secret");
        fetch.mockResolvedValueOnce({ ok: false, status: 401, statusText: "Unauthorized", url: "/api/x", json: vi.fn().mockRejectedValue(new Error()) });
        await expect(api.snapshot()).rejects.toThrow("401 Unauthorized");
        expect(localStorage.getItem("monori_token")).toBeNull();
    });
});
