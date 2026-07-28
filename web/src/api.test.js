import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";

const ok = (body = {}) => ({
    ok: true,
    json: vi.fn().mockResolvedValue(body),
    blob: vi.fn().mockResolvedValue(new Blob(["x"])),
});

/** Every JSON endpoint, as [label, call, expected url, expected method, expected body]. */
const ENDPOINTS = [
    [
        "snapshot",
        () => api.snapshot({ light: true, limit: 5 }),
        "/api/snapshot?light=1&limit=5",
        undefined,
        undefined,
    ],
    [
        "transactions",
        () => api.transactions({ limit: 2, offset: 3 }),
        "/api/transactions?limit=2&offset=3",
        undefined,
        undefined,
    ],
    ["putBudget", () => api.putBudget({ categoryId: 1 }), "/api/budgets", "PUT", { categoryId: 1 }],
    [
        "bulkBudgets",
        () => api.bulkBudgets([{ categoryId: 1, month: 1 }]),
        "/api/budgets/bulk",
        "POST",
        { cells: [{ categoryId: 1, month: 1 }] },
    ],
    [
        "hiddenTx",
        () => api.hiddenTx(20),
        "/api/transactions?hidden=true&limit=1000&offset=20",
        undefined,
        undefined,
    ],
    [
        "createTx",
        () => api.createTx({ amount: 17, description: "Coffee" }),
        "/api/transactions",
        "POST",
        { amount: 17, description: "Coffee" },
    ],
    [
        "patchTx",
        () => api.patchTx(1, { categoryId: 2 }),
        "/api/transactions/1",
        "PATCH",
        { categoryId: 2 },
    ],
    ["deleteTx", () => api.deleteTx(1), "/api/transactions/1", "DELETE", undefined],
    [
        "createAccount",
        () => api.createAccount({ name: "Card" }),
        "/api/accounts",
        "POST",
        { name: "Card" },
    ],
    [
        "patchAccount",
        () => api.patchAccount(1, { name: "Cash" }),
        "/api/accounts/1",
        "PATCH",
        { name: "Cash" },
    ],
    [
        "deleteAccount",
        () => api.deleteAccount(1, 2),
        "/api/accounts/1?reassignTo=2",
        "DELETE",
        undefined,
    ],
    [
        "reorderAccounts",
        () => api.reorderAccounts([2, 1]),
        "/api/accounts/reorder",
        "POST",
        { ids: [2, 1] },
    ],
    [
        "reconcileAccount",
        () => api.reconcileAccount(1, 50),
        "/api/accounts/1/reconcile",
        "POST",
        { actualBalance: 50 },
    ],
    [
        "createTransfer",
        () => api.createTransfer({ amount: 10 }),
        "/api/transfers",
        "POST",
        { amount: 10 },
    ],
    ["splitTransfer", () => api.splitTransfer("t"), "/api/transfers/t", "DELETE", undefined],
    [
        "linkTransfer",
        () => api.linkTransfer({ sourceId: 1, targetId: 2 }),
        "/api/transfers/link",
        "POST",
        { sourceId: 1, targetId: 2 },
    ],
    [
        "transferSuggestions",
        () => api.transferSuggestions(),
        "/api/transfers/suggestions",
        undefined,
        undefined,
    ],
    [
        "dismissTransferSuggestion",
        () => api.dismissTransferSuggestion({ sourceId: 1, targetId: 2 }),
        "/api/transfers/suggestions/dismiss",
        "POST",
        { sourceId: 1, targetId: 2 },
    ],
    ["detectTransfers", () => api.detectTransfers(), "/api/transfers/detect", "POST", undefined],
    [
        "createCategory",
        () => api.createCategory({ name: "Food" }),
        "/api/categories",
        "POST",
        { name: "Food" },
    ],
    [
        "patchCategory",
        () => api.patchCategory(1, { name: "Home" }),
        "/api/categories/1",
        "PATCH",
        { name: "Home" },
    ],
    ["deleteCategory", () => api.deleteCategory(1), "/api/categories/1", "DELETE", undefined],
    // the merge target goes in the body, not the path — swapping them silently
    // merges the wrong way round
    [
        "mergeCategory",
        () => api.mergeCategory(1, 2),
        "/api/categories/1/merge",
        "POST",
        { into: 2 },
    ],
    [
        "reorderCategories",
        () => api.reorderCategories([1]),
        "/api/categories/reorder",
        "POST",
        { ids: [1] },
    ],
    [
        "createGroup",
        () => api.createGroup({ name: "Living" }),
        "/api/groups",
        "POST",
        { name: "Living" },
    ],
    [
        "patchGroup",
        () => api.patchGroup(1, { name: "Home" }),
        "/api/groups/1",
        "PATCH",
        { name: "Home" },
    ],
    ["deleteGroup", () => api.deleteGroup(1), "/api/groups/1", "DELETE", undefined],
    ["reorderGroups", () => api.reorderGroups([1]), "/api/groups/reorder", "POST", { ids: [1] }],
    [
        "importPreview",
        () => api.importPreview("rows"),
        "/api/import/preview",
        "POST",
        { text: "rows" },
    ],
    [
        "importDuplicates",
        () => api.importDuplicates([{ date: "2024-01-01", amount: 11 }]),
        "/api/import/duplicates",
        "POST",
        { rows: [{ date: "2024-01-01", amount: 11 }] },
    ],
    [
        "importCommit",
        () => api.importCommit([{ id: 3 }]),
        "/api/import/commit",
        "POST",
        { rows: [{ id: 3 }], accountId: null },
    ],
    [
        "connectionsAvailable",
        () => api.connectionsAvailable(),
        "/api/connections/available",
        undefined,
        undefined,
    ],
    [
        "createConnection",
        () => api.createConnection({ provider: "bank" }),
        "/api/connections",
        "POST",
        { provider: "bank" },
    ],
    ["deleteConnection", () => api.deleteConnection(1), "/api/connections/1", "DELETE", undefined],
    ["syncConnection", () => api.syncConnection(1), "/api/connections/1/sync", "POST", undefined],
    [
        "submitConnectionSms",
        () => api.submitConnectionSms(1, "1234"),
        "/api/connections/1/sms",
        "POST",
        { code: "1234" },
    ],
    [
        "cancelConnectionSync",
        () => api.cancelConnectionSync(1),
        "/api/connections/1/cancel",
        "POST",
        undefined,
    ],
    [
        "authRegister",
        () => api.authRegister("a@b.c", "pw"),
        "/api/auth/register",
        "POST",
        { email: "a@b.c", password: "pw" },
    ],
    ["adminOverview", () => api.adminOverview(), "/api/admin/overview", undefined, undefined],
    ["adminUsers", () => api.adminUsers(), "/api/admin/users", undefined, undefined],
    ["adminUserDetail", () => api.adminUserDetail(1), "/api/admin/users/1", undefined, undefined],
    [
        "adminUserTransactions",
        () => api.adminUserTransactions(1, { limit: 2, offset: 3 }),
        "/api/admin/users/1/transactions?limit=2&offset=3",
        undefined,
        undefined,
    ],
    [
        "adminDeleteUserTransactions",
        () => api.adminDeleteUserTransactions(1, [2]),
        "/api/admin/users/1/transactions/delete",
        "POST",
        { ids: [2] },
    ],
    ["adminActivity", () => api.adminActivity(), "/api/admin/activity", undefined, undefined],
    [
        "adminSql",
        () => api.adminSql("select 1", true, true),
        "/api/admin/sql",
        "POST",
        { sql: "select 1", confirmWrite: true, dryRun: true },
    ],
    ["adminDeleteUser", () => api.adminDeleteUser(1), "/api/admin/users/1", "DELETE", undefined],
];

describe("api", () => {
    let fetch;
    beforeEach(() => {
        const values = new Map();
        vi.stubGlobal("localStorage", {
            getItem: (k) => values.get(k) ?? null,
            setItem: (k, v) => values.set(k, v),
            removeItem: (k) => values.delete(k),
            clear: () => values.clear(),
        });
        fetch = vi.fn().mockResolvedValue(ok({ id: 7, transferId: "t" }));
        vi.stubGlobal("fetch", fetch);
    });
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it.each(ENDPOINTS)(
        "calls %s with the right url, method and body",
        async (_label, call, url, method, body) => {
            localStorage.setItem("monori_token", "secret");
            await call();

            expect(fetch).toHaveBeenCalledTimes(1);
            const [actualUrl, options] = fetch.mock.calls[0];
            expect(actualUrl).toBe(url);
            expect(options.method).toBe(method);
            expect(options.headers.Authorization).toBe("Bearer secret");

            if (body === undefined) {
                expect(options.body).toBeUndefined();
            } else {
                expect(options.headers["Content-Type"]).toBe("application/json");
                expect(JSON.parse(options.body)).toEqual(body);
            }
        },
    );

    // the token grant is form-encoded and calls the email "username" — a JSON
    // body or a "email" field is rejected by the OAuth2 endpoint
    it("posts the login as an OAuth2 password grant", async () => {
        await api.authLogin("a@b.c", "hunter2");
        const [url, options] = fetch.mock.calls[0];
        expect(url).toBe("/api/auth/token");
        expect(options.method).toBe("POST");
        expect(options.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
        expect(options.body).toBeInstanceOf(URLSearchParams);
        expect(options.body.get("username")).toBe("a@b.c");
        expect(options.body.get("password")).toBe("hunter2");
        expect([...options.body.keys()].sort()).toEqual(["password", "username"]);
    });

    it("authenticates authMe with the token it is handed, not the stored one", async () => {
        localStorage.setItem("monori_token", "stored");
        await api.authMe("explicit");
        const [url, options] = fetch.mock.calls[0];
        expect(url).toBe("/api/auth/me");
        expect(options.headers.Authorization).toBe("Bearer explicit");
    });

    it("sends no Authorization header when there is no token", async () => {
        await api.snapshot();
        expect(fetch.mock.calls[0][1].headers).toEqual({});
    });

    it("uses defaults, handles multipart payloads and downloads exports", async () => {
        await api.snapshot();
        expect(fetch.mock.calls[0][0]).toBe("/api/snapshot");
        await api.transactions();
        expect(fetch.mock.calls[1][0]).toBe("/api/transactions?limit=1000&offset=0");
        await api.deleteAccount(1);
        expect(fetch.mock.calls[2][0]).toBe("/api/accounts/1");

        await api.workbookPreview(new File(["x"], "book.xlsx"));
        const [previewUrl, previewOpts] = fetch.mock.calls[3];
        expect(previewUrl).toBe("/api/import/workbook/preview");
        expect(previewOpts.body).toBeInstanceOf(FormData);
        expect(previewOpts.body.get("file").name).toBe("book.xlsx");

        await api.workbookCommit(new File(["x"], "book.xlsx"), { card: 1 }, "skip");
        const [commitUrl, commitOpts] = fetch.mock.calls[4];
        expect(commitUrl).toBe("/api/import/workbook/commit");
        expect(commitOpts.body.get("mapping")).toBe('{"card":1}');
        expect(commitOpts.body.get("budgetPolicy")).toBe("skip");

        const blob = await api.exportXlsx();
        expect(blob).toBeInstanceOf(Blob);
        expect(fetch.mock.calls[5][0]).toBe("/api/export/xlsx");
    });

    it("sends explicit false admin SQL safeguards by default", async () => {
        await api.adminSql("select 1");
        const [, options] = fetch.mock.calls[0];
        expect(JSON.parse(options.body)).toEqual({
            sql: "select 1",
            confirmWrite: false,
            dryRun: false,
        });
    });

    it("reports an export failure by status instead of returning a blob", async () => {
        fetch.mockResolvedValueOnce({ ok: false, status: 500, statusText: "Server Error" });
        await expect(api.exportXlsx()).rejects.toThrow("500 Server Error");
    });

    it("prefers the server's detail message over the bare status", async () => {
        fetch.mockResolvedValueOnce({
            ok: false,
            status: 400,
            statusText: "Bad",
            url: "/api/x",
            json: vi.fn().mockResolvedValue({ detail: "Bad input" }),
        });
        await expect(api.snapshot()).rejects.toThrow("Bad input");
    });

    it("uses the status when JSON has no detail", async () => {
        fetch.mockResolvedValueOnce({
            ok: false,
            status: 500,
            statusText: "Internal Server Error",
            url: "/api/x",
            json: vi.fn().mockResolvedValue({ message: "hidden" }),
        });
        await expect(api.snapshot()).rejects.toThrow("500 Internal Server Error");
    });

    it("falls back to the status when the error body is unreadable", async () => {
        fetch.mockResolvedValueOnce({
            ok: false,
            status: 500,
            statusText: "Server Error",
            url: "/api/x",
            json: vi.fn().mockRejectedValue(new Error("not json")),
        });
        await expect(api.snapshot()).rejects.toThrow("500 Server Error");
    });

    describe("an expired session", () => {
        let replace;
        beforeEach(() => {
            replace = vi.fn();
            vi.stubGlobal("location", { replace });
        });

        const unauthorized = (url) => ({
            ok: false,
            status: 401,
            statusText: "Unauthorized",
            url,
            json: vi.fn().mockRejectedValue(new Error()),
        });

        it("drops the token and sends the user to the login page", async () => {
            localStorage.setItem("monori_token", "secret");
            fetch.mockResolvedValueOnce(unauthorized("/api/snapshot"));
            await expect(api.snapshot()).rejects.toThrow("401 Unauthorized");
            expect(localStorage.getItem("monori_token")).toBeNull();
            expect(replace).toHaveBeenCalledWith("/login");
        });

        // a rejected login is just a wrong password: bouncing the user off the
        // login page they are already on would lose what they typed
        it("leaves the session alone when the auth endpoint itself says 401", async () => {
            localStorage.setItem("monori_token", "secret");
            fetch.mockResolvedValueOnce(unauthorized("/api/auth/token"));
            await expect(api.authLogin("a@b.c", "wrong")).rejects.toThrow("401 Unauthorized");
            expect(localStorage.getItem("monori_token")).toBe("secret");
            expect(replace).not.toHaveBeenCalled();
        });

        it("leaves the session alone when authMe says 401", async () => {
            localStorage.setItem("monori_token", "secret");
            fetch.mockResolvedValueOnce(unauthorized("/api/auth/me"));
            await expect(api.authMe("secret")).rejects.toThrow("401 Unauthorized");
            expect(localStorage.getItem("monori_token")).toBe("secret");
            expect(replace).not.toHaveBeenCalled();
        });

        // nothing to expire when the user was never signed in
        it("does not redirect an anonymous caller", async () => {
            fetch.mockResolvedValueOnce(unauthorized("/api/snapshot"));
            await expect(api.snapshot()).rejects.toThrow("401 Unauthorized");
            expect(replace).not.toHaveBeenCalled();
        });

        it("leaves the session alone for a non-401 failure", async () => {
            localStorage.setItem("monori_token", "secret");
            fetch.mockResolvedValueOnce({
                ok: false,
                status: 403,
                statusText: "Forbidden",
                url: "/api/snapshot",
                json: vi.fn().mockRejectedValue(new Error()),
            });
            await expect(api.snapshot()).rejects.toThrow("403 Forbidden");
            expect(localStorage.getItem("monori_token")).toBe("secret");
            expect(replace).not.toHaveBeenCalled();
        });
    });
});
