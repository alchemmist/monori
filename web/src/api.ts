import type {
    AccountCreate,
    AccountPatch,
    BudgetCell,
    CategoryCreate,
    CategoryPatch,
    Id,
    ImportPreview,
    ImportResult,
    ImportRow,
    Snapshot,
    SyncResult,
    Transaction,
    TransactionCreate,
    TransactionPage,
    TransactionPatch,
    TransactionSplit,
    TransferCreate,
    TransferPair,
    TransferSuggestion,
    User,
    AvailableConnector,
    WorkbookPreview,
    WorkbookResult,
    AdminActivity,
    AdminOverview,
    AdminSqlResult,
    AdminTransaction,
    AdminUserDetail,
    AdminUserSummary,
} from "./types.js";

const tokenHeader = (): Record<string, string> => {
    const token = localStorage.getItem("monori_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
};

const apiFetch = (url: string, opts: RequestInit = {}) => {
    const headers = {
        ...tokenHeader(),
        ...(opts.headers as Record<string, string> | undefined),
    };
    return fetch(url, { ...opts, headers });
};

const json = async <T = never>(r: Response): Promise<T> => {
    if (!r.ok) {
        if (
            r.status === 401 &&
            !r.url.includes("/api/auth/") &&
            localStorage.getItem("monori_token")
        ) {
            localStorage.removeItem("monori_token");
            window.location.replace("/login");
        }
        let detail = `${r.status} ${r.statusText}`;
        try {
            const body: unknown = await r.json();
            if (
                typeof body === "object" &&
                body !== null &&
                "detail" in body &&
                typeof body.detail === "string"
            ) {
                detail = body.detail;
            }
        } catch {
            detail = `${r.status} ${r.statusText}`;
        }
        throw new Error(detail);
    }
    return (await r.json()) as T;
};

interface OkResponse {
    ok?: boolean;
    set?: number;
}

interface IdResponse {
    id: Id;
}

interface TransferResponse {
    transferId: string;
}

interface SplitResponse {
    splits: TransactionSplit[];
}

export const api = {
    snapshot: ({
        light = false,
        limit,
    }: { light?: boolean; limit?: number } = {}): Promise<Snapshot> => {
        const qs = new URLSearchParams();
        if (light) qs.set("light", "1");
        if (limit) qs.set("limit", String(limit));
        const q = qs.toString();
        return apiFetch(`/api/snapshot${q ? `?${q}` : ""}`).then(json);
    },
    transactions: ({
        limit = 1000,
        offset = 0,
    }: { limit?: number; offset?: number } = {}): Promise<TransactionPage> =>
        apiFetch(`/api/transactions?limit=${limit}&offset=${offset}`).then(json),
    putBudget: (cell: BudgetCell): Promise<OkResponse> =>
        apiFetch("/api/budgets", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(cell),
        }).then(json),
    bulkBudgets: (cells: BudgetCell[]): Promise<OkResponse> =>
        apiFetch("/api/budgets/bulk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cells }),
        }).then(json),
    hiddenTx: (offset = 0): Promise<TransactionPage> =>
        apiFetch(`/api/transactions?hidden=true&limit=1000&offset=${offset}`).then(json),
    createTx: (body: TransactionCreate): Promise<IdResponse> =>
        apiFetch("/api/transactions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    patchTx: (id: Id, patch: TransactionPatch): Promise<OkResponse> =>
        apiFetch(`/api/transactions/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    replaceTxSplits: (id: Id, parts: Array<Omit<TransactionSplit, "id">>): Promise<SplitResponse> =>
        apiFetch(`/api/transactions/${id}/splits`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ parts }),
        }).then(json),
    deleteTx: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/transactions/${id}`, { method: "DELETE" }).then(json),
    createAccount: (body: AccountCreate): Promise<IdResponse> =>
        apiFetch("/api/accounts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    patchAccount: (id: Id, patch: AccountPatch): Promise<OkResponse> =>
        apiFetch(`/api/accounts/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    deleteAccount: (id: Id, reassignTo?: Id | null): Promise<OkResponse> =>
        apiFetch(`/api/accounts/${id}${reassignTo ? `?reassignTo=${reassignTo}` : ""}`, {
            method: "DELETE",
        }).then(json),
    reorderAccounts: (ids: Id[]): Promise<void> =>
        apiFetch("/api/accounts/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        })
            .then(json<OkResponse>)
            .then(() => undefined),
    reconcileAccount: (id: Id, actualBalance: number): Promise<{ delta: number }> =>
        apiFetch(`/api/accounts/${id}/reconcile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ actualBalance }),
        }).then(json),
    createTransfer: (body: TransferCreate): Promise<TransferResponse> =>
        apiFetch("/api/transfers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    // DELETE splits the transfer back into two ordinary transactions; the rows
    // are never removed, since half of them came from a bank
    splitTransfer: (transferId: string): Promise<OkResponse> =>
        apiFetch(`/api/transfers/${transferId}`, { method: "DELETE" }).then(json),
    linkTransfer: (body: TransferPair): Promise<TransferResponse> =>
        apiFetch("/api/transfers/link", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    transferSuggestions: (): Promise<{ rows: TransferSuggestion[]; transactions: Transaction[] }> =>
        apiFetch("/api/transfers/suggestions").then(json),
    dismissTransferSuggestion: (body: TransferPair): Promise<OkResponse> =>
        apiFetch("/api/transfers/suggestions/dismiss", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    detectTransfers: (): Promise<{ merged: string[]; suggested: number }> =>
        apiFetch("/api/transfers/detect", { method: "POST" }).then(json),
    createCategory: (body: CategoryCreate): Promise<IdResponse> =>
        apiFetch("/api/categories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    patchCategory: (id: Id, patch: CategoryPatch): Promise<OkResponse> =>
        apiFetch(`/api/categories/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    archiveGoal: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/categories/${id}/archive-goal`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        }).then(json),
    deleteCategory: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/categories/${id}`, { method: "DELETE" }).then(json),
    mergeCategory: (id: Id, into: Id): Promise<OkResponse> =>
        apiFetch(`/api/categories/${id}/merge`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ into }),
        }).then(json),
    reorderCategories: (ids: Id[]): Promise<OkResponse> =>
        apiFetch("/api/categories/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json),
    createGroup: (body: { name: string; kind: string }): Promise<IdResponse> =>
        apiFetch("/api/groups", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    patchGroup: (id: Id, patch: { name?: string; kind?: string }): Promise<OkResponse> =>
        apiFetch(`/api/groups/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    deleteGroup: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/groups/${id}`, { method: "DELETE" }).then(json),
    reorderGroups: (ids: Id[]): Promise<OkResponse> =>
        apiFetch("/api/groups/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json),
    importPreview: (text: string, accountId: Id | null = null): Promise<ImportPreview> =>
        apiFetch("/api/import/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, accountId }),
        }).then(json),
    importDuplicates: (
        rows: Array<Pick<ImportRow, "date" | "amount"> & Partial<ImportRow>>,
    ): Promise<{ duplicates: boolean[] }> =>
        apiFetch("/api/import/duplicates", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rows }),
        }).then(json),
    importCommit: (
        rows: Array<Partial<ImportRow> & { id?: Id }>,
        accountId: Id | null = null,
    ): Promise<ImportResult> =>
        apiFetch("/api/import/commit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rows, accountId }),
        }).then(json),
    connectionsAvailable: (): Promise<AvailableConnector[]> =>
        apiFetch("/api/connections/available").then(json),
    createConnection: (body: {
        bank: string;
        kind: string;
        credentials: Record<string, string>;
    }): Promise<IdResponse> =>
        apiFetch("/api/connections", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    deleteConnection: (id: Id): Promise<{ deleted: Id }> =>
        apiFetch(`/api/connections/${id}`, { method: "DELETE" }).then(json),
    syncConnection: (id: Id): Promise<SyncResult> =>
        apiFetch(`/api/connections/${id}/sync`, { method: "POST" }).then(json),
    submitConnectionSms: (id: Id, code: string): Promise<SyncResult> =>
        apiFetch(`/api/connections/${id}/sms`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code }),
        }).then(json),
    cancelConnectionSync: (id: Id): Promise<{ cancelled: Id }> =>
        apiFetch(`/api/connections/${id}/cancel`, { method: "POST" }).then(json),
    authRegister: (email: string, password: string): Promise<User> =>
        apiFetch("/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        }).then(json),
    authLogin: (email: string, password: string): Promise<{ access_token: string }> => {
        // OAuth2 password grant is form-encoded, username = email
        const form = new URLSearchParams();
        form.set("username", email);
        form.set("password", password);
        return apiFetch("/api/auth/token", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: form,
        }).then(json);
    },
    authMe: (token: string): Promise<User> =>
        apiFetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } }).then(json),
    authPatchMe: (patch: Partial<Pick<User, "defaultAccountId">>): Promise<User> =>
        apiFetch("/api/auth/me", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    exportXlsx: async () => {
        const r = await apiFetch("/api/export/xlsx");
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.blob();
    },
    workbookPreview: (file: File): Promise<WorkbookPreview> => {
        const form = new FormData();
        form.append("file", file);
        return apiFetch("/api/import/workbook/preview", { method: "POST", body: form }).then(json);
    },
    adminOverview: (): Promise<AdminOverview> => apiFetch("/api/admin/overview").then(json),
    adminUsers: (): Promise<AdminUserSummary[]> => apiFetch("/api/admin/users").then(json),
    adminUserDetail: (id: Id): Promise<AdminUserDetail> =>
        apiFetch(`/api/admin/users/${id}`).then(json),
    adminUserTransactions: (
        id: Id,
        { limit = 1000, offset = 0 }: { limit?: number; offset?: number } = {},
    ): Promise<AdminTransaction[]> =>
        apiFetch(`/api/admin/users/${id}/transactions?limit=${limit}&offset=${offset}`).then(json),
    adminDeleteUserTransactions: (id: Id, ids: Id[]): Promise<{ deleted: number }> =>
        apiFetch(`/api/admin/users/${id}/transactions/delete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json),
    adminActivity: (): Promise<AdminActivity> => apiFetch("/api/admin/activity").then(json),
    adminSql: (sql: string, confirmWrite = false, dryRun = false): Promise<AdminSqlResult> =>
        apiFetch("/api/admin/sql", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sql, confirmWrite, dryRun }),
        }).then(json),
    adminDeleteUser: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/admin/users/${id}`, { method: "DELETE" }).then(json),
    workbookCommit: (
        file: File,
        mapping: Record<string, number>,
        budgetPolicy: string,
        remember = false,
    ): Promise<WorkbookResult> => {
        const form = new FormData();
        form.append("file", file);
        form.append("mapping", JSON.stringify(mapping));
        form.append("budgetPolicy", budgetPolicy);
        form.append("remember", String(remember));
        return apiFetch("/api/import/workbook/commit", { method: "POST", body: form }).then(json);
    },
};
