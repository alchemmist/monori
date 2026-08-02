import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Mock } from "vitest";
import { api } from "./api.js";

const ok = (body: unknown = {}) => ({
    ok: true,
    json: vi.fn().mockResolvedValue(body),
    blob: vi.fn().mockResolvedValue(new Blob(["x"])),
});

const requireString = (value: unknown): string => {
    if (typeof value !== "string") throw new Error("expected a string request body");
    return value;
};

const requireFormData = (value: unknown): FormData => {
    if (!(value instanceof FormData)) throw new Error("expected a multipart request body");
    return value;
};

const requireFile = (value: FormDataEntryValue | null): File => {
    if (!(value instanceof File)) throw new Error("expected a file form field");
    return value;
};

const userResponse = {
    id: 1,
    email: "user@example.com",
    createdAt: "2026-01-01T00:00:00",
    isAdmin: false,
    lastLogin: null,
    defaultAccountId: null,
};

const connectionResponse = {
    id: 1,
    bank: "bank",
    kind: "browser",
    status: "disconnected",
    lastSync: null,
    lastError: null,
    hasCredentials: true,
    createdAt: "2026-01-01T00:00:00",
    updatedAt: "2026-01-01T00:00:00",
};

const snapshotResponse = {
    accounts: [],
    groups: [],
    categories: [],
    transactions: [],
    transactionsTotal: 0,
    transfers: [],
    budgets: [],
    connections: [],
};

const responseFor = (url: string, method?: string): unknown => {
    if (url.startsWith("/api/snapshot")) return snapshotResponse;
    if (url.startsWith("/api/transactions?")) return { total: 0, rows: [] };
    if (url.endsWith("/splits")) return { splits: [] };
    if (url === "/api/budgets/bulk") return { set: 1 };
    if (url === "/api/accounts/1/reconcile") return { delta: 0 };
    if (url === "/api/transfers/suggestions") return { rows: [], transactions: [] };
    if (url === "/api/transfers/detect") return { merged: [], suggested: 0 };
    if (url === "/api/transfers" || url === "/api/transfers/link") return { transfer_id: "t" };
    if (url === "/api/import/preview") return { rows: [], errors: [] };
    if (url === "/api/import/duplicates") return { duplicates: [] };
    if (url === "/api/import/commit")
        return { inserted: 0, skipped: 0, transfersMerged: 0, transfersSuggested: 0 };
    if (url === "/api/import/workbook/preview")
        return {
            groups: 0,
            categories: 0,
            transactions: 0,
            transactionsByYear: {},
            budgetCells: 0,
            accountSlots: [],
            warnings: [],
            errors: [],
            budgetConflicts: 0,
        };
    if (url === "/api/import/workbook/commit")
        return {
            groupsCreated: 0,
            categoriesCreated: 0,
            inserted: 0,
            skipped: 0,
            batches: [],
            budgetsWritten: 0,
            budgetsSkipped: 0,
            warnings: [],
            errors: [],
            cardTailsBound: 0,
        };
    if (url === "/api/connections/available") return [];
    if (url === "/api/connections") return connectionResponse;
    if (url.endsWith("/sync") || url.endsWith("/sms"))
        return {
            status: "connected",
            inserted: 0,
            skipped: 0,
            accounts: [],
            dateFrom: null,
            dateTo: null,
            unmappedTails: [],
        };
    if (url.endsWith("/cancel")) return { cancelled: 1 };
    if (url === "/api/connections/1") return { deleted: 1 };
    if (url === "/api/auth/token") return { access_token: "token", token_type: "bearer" };
    if (url.startsWith("/api/auth/")) return userResponse;
    if (url === "/api/admin/overview")
        return {
            totals: { users: 0, transactions: 0, accounts: 0, connections: 0 },
            dbSizeBytes: 0,
            newUsers7d: 0,
            newUsers30d: 0,
            activeUsers7d: 0,
            registrations: [],
        };
    if (url === "/api/admin/users") return [];
    if (url === "/api/admin/users/1" && method !== "DELETE")
        return {
            user: userResponse,
            accounts: [],
            recentTransactions: [],
            featureUsage: [],
            recentLogins: [],
        };
    if (url.startsWith("/api/admin/users/1/transactions?")) return [];
    if (url === "/api/admin/users/1/transactions/delete") return { deleted: 1 };
    if (url === "/api/admin/activity") return { features: [], daily: [], recentLogins: [] };
    if (url === "/api/admin/sql")
        return { kind: "read", columns: [], rows: [], rowCount: 0, truncated: false, elapsedMs: 0 };
    if (
        url === "/api/transactions" ||
        url === "/api/accounts" ||
        url === "/api/categories" ||
        url === "/api/groups"
    )
        return { id: 7 };
    return { ok: true };
};

/** Every JSON endpoint, as [label, call, expected url, expected method, expected body]. */
type Endpoint = [string, () => Promise<unknown>, string, string | undefined, unknown];

const ENDPOINTS: Endpoint[] = [
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
    [
        "putBudget",
        () => api.putBudget({ categoryId: 1, year: 2026, month: 1, amount: 10 }),
        "/api/budgets",
        "PUT",
        { categoryId: 1, year: 2026, month: 1, amount: 10 },
    ],
    [
        "bulkBudgets",
        () => api.bulkBudgets([{ categoryId: 1, year: 2026, month: 1, amount: 10 }]),
        "/api/budgets/bulk",
        "POST",
        { cells: [{ categoryId: 1, year: 2026, month: 1, amount: 10 }] },
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
        () => api.createTx({ date: "2026-01-01", accountId: 1, amount: 17, description: "Coffee" }),
        "/api/transactions",
        "POST",
        { date: "2026-01-01", accountId: 1, amount: 17, description: "Coffee" },
    ],
    [
        "patchTx",
        () => api.patchTx(1, { categoryId: 2 }),
        "/api/transactions/1",
        "PATCH",
        { categoryId: 2 },
    ],
    [
        "replaceTxSplits",
        () =>
            api.replaceTxSplits(1, [
                { categoryId: 1, amount: 5, comment: "" },
                { categoryId: 2, amount: 6, comment: "" },
            ]),
        "/api/transactions/1/splits",
        "PUT",
        {
            parts: [
                { categoryId: 1, amount: 5, comment: "" },
                { categoryId: 2, amount: 6, comment: "" },
            ],
        },
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
        () =>
            api.createTransfer({
                fromAccountId: 1,
                toAccountId: 2,
                amount: 10,
                date: "2026-01-01",
            }),
        "/api/transfers",
        "POST",
        { fromAccountId: 1, toAccountId: 2, amount: 10, date: "2026-01-01" },
    ],
    ["splitTransfer", () => api.splitTransfer("t"), "/api/transfers/t", "DELETE", undefined],
    [
        "linkTransfer",
        () => api.linkTransfer({ outTxId: 1, inTxId: 2 }),
        "/api/transfers/link",
        "POST",
        { outTxId: 1, inTxId: 2 },
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
        () => api.dismissTransferSuggestion({ outTxId: 1, inTxId: 2 }),
        "/api/transfers/suggestions/dismiss",
        "POST",
        { outTxId: 1, inTxId: 2 },
    ],
    ["detectTransfers", () => api.detectTransfers(), "/api/transfers/detect", "POST", undefined],
    [
        "createCategory",
        () => api.createCategory({ name: "Food", groupId: 1 }),
        "/api/categories",
        "POST",
        { name: "Food", groupId: 1 },
    ],
    [
        "patchCategory",
        () => api.patchCategory(1, { name: "Home" }),
        "/api/categories/1",
        "PATCH",
        { name: "Home" },
    ],
    ["archiveGoal", () => api.archiveGoal(7), "/api/categories/7/archive-goal", "POST", {}],
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
        () => api.createGroup({ name: "Living", kind: "expense" }),
        "/api/groups",
        "POST",
        { name: "Living", kind: "expense" },
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
        { text: "rows", accountId: null },
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
        () => api.createConnection({ bank: "bank", kind: "browser", credentials: {} }),
        "/api/connections",
        "POST",
        { bank: "bank", kind: "browser", credentials: {} },
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
    [
        "authPatchMe",
        () => api.authPatchMe({ defaultAccountId: 3 }),
        "/api/auth/me",
        "PATCH",
        { defaultAccountId: 3 },
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
    type FetchOptions = {
        method?: string;
        headers: Record<string, string>;
        body?: string | FormData | URLSearchParams;
    };
    type TestFetch = (url: string, options: FetchOptions) => Promise<unknown>;
    let fetch: Mock<TestFetch>;
    beforeEach(() => {
        const values = new Map<string, string>();
        vi.stubGlobal("localStorage", {
            getItem: (key: string) => values.get(key) ?? null,
            setItem: (key: string, value: string) => values.set(key, value),
            removeItem: (key: string) => values.delete(key),
            clear: () => values.clear(),
        });
        fetch = vi
            .fn<TestFetch>()
            .mockImplementation(async (url, options) => ok(responseFor(url, options.method)));
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
            const [actualUrl, options] = fetch.mock.calls[0]!;
            expect(actualUrl).toBe(url);
            expect(options.method).toBe(method);
            expect(options.headers["Authorization"]).toBe("Bearer secret");

            if (body === undefined) {
                expect(options.body).toBeUndefined();
            } else {
                expect(options.headers["Content-Type"]).toBe("application/json");
                expect(JSON.parse(requireString(options.body))).toEqual(body);
            }
        },
    );

    it.each(ENDPOINTS)("rejects an invalid %s response at runtime", async (_label, call) => {
        fetch.mockResolvedValueOnce(ok(null));
        await expect(call()).rejects.toThrow();
    });

    it.each([
        ["authLogin", () => api.authLogin("a@b.c", "pw")],
        ["authMe", () => api.authMe("token")],
        ["workbookPreview", () => api.workbookPreview(new File(["x"], "book.xlsx"))],
        ["workbookCommit", () => api.workbookCommit(new File(["x"], "book.xlsx"), {}, "skip")],
    ] satisfies Array<[string, () => Promise<unknown>]>)(
        "rejects an invalid %s response at runtime",
        async (_label, call) => {
            fetch.mockResolvedValueOnce(ok(null));
            await expect(call()).rejects.toThrow();
        },
    );

    // the token grant is form-encoded and calls the email "username" — a JSON
    // body or a "email" field is rejected by the OAuth2 endpoint
    it("posts the login as an OAuth2 password grant", async () => {
        await api.authLogin("a@b.c", "hunter2");
        const [url, options] = fetch.mock.calls[0]!;
        expect(url).toBe("/api/auth/token");
        expect(options.method).toBe("POST");
        expect(options.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
        expect(options.body).toBeInstanceOf(URLSearchParams);
        if (!(options.body instanceof URLSearchParams))
            throw new Error("expected an URL-encoded request body");
        const form = options.body;
        expect(form.get("username")).toBe("a@b.c");
        expect(form.get("password")).toBe("hunter2");
        expect([...form.keys()].sort()).toEqual(["password", "username"]);
    });

    it("authenticates authMe with the token it is handed, not the stored one", async () => {
        localStorage.setItem("monori_token", "stored");
        await api.authMe("explicit");
        const [url, options] = fetch.mock.calls[0]!;
        expect(url).toBe("/api/auth/me");
        expect(options.headers["Authorization"]).toBe("Bearer explicit");
    });

    it("sends no Authorization header when there is no token", async () => {
        await api.snapshot();
        expect(fetch.mock.calls[0]![1].headers).toEqual({});
    });

    it("uses defaults, handles multipart payloads and downloads exports", async () => {
        await api.snapshot();
        expect(fetch.mock.calls[0]![0]).toBe("/api/snapshot");
        await api.transactions();
        expect(fetch.mock.calls[1]![0]).toBe("/api/transactions?limit=1000&offset=0");
        await api.deleteAccount(1);
        expect(fetch.mock.calls[2]![0]).toBe("/api/accounts/1");

        await api.workbookPreview(new File(["x"], "book.xlsx"));
        const [previewUrl, previewOpts] = fetch.mock.calls[3]!;
        expect(previewUrl).toBe("/api/import/workbook/preview");
        expect(previewOpts.body).toBeInstanceOf(FormData);
        const previewForm = requireFormData(previewOpts.body);
        expect(previewForm.get("file")).toBeInstanceOf(File);
        expect(requireFile(previewForm.get("file")).name).toBe("book.xlsx");

        await api.workbookCommit(new File(["x"], "book.xlsx"), { card: 1 }, "skip");
        const [commitUrl, commitOpts] = fetch.mock.calls[4]!;
        expect(commitUrl).toBe("/api/import/workbook/commit");
        const commitForm = requireFormData(commitOpts.body);
        expect(commitForm.get("mapping")).toBe('{"card":1}');
        expect(commitForm.get("budgetPolicy")).toBe("skip");

        const blob = await api.exportXlsx();
        expect(blob).toBeInstanceOf(Blob);
        expect(fetch.mock.calls[5]![0]).toBe("/api/export/xlsx");
    });

    it("routes an import to a chosen account instead of the null default", async () => {
        await api.importCommit([{ id: 3 }], 8);
        const [url, options] = fetch.mock.calls[0]!;
        expect(url).toBe("/api/import/commit");
        expect(JSON.parse(requireString(options.body))).toEqual({
            rows: [{ id: 3 }],
            accountId: 8,
        });
    });

    it("sends explicit false admin SQL safeguards by default", async () => {
        await api.adminSql("select 1");
        const [, options] = fetch.mock.calls[0]!;
        expect(JSON.parse(requireString(options.body))).toEqual({
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
        let replace: ReturnType<typeof vi.fn>;
        beforeEach(() => {
            replace = vi.fn();
            vi.stubGlobal("location", { replace });
        });

        const unauthorized = (url: string) => ({
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
