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
import { z } from "zod";
import {
    adminActivitySchema,
    adminOverviewSchema,
    adminSqlResultSchema,
    adminTransactionSchema,
    adminUserDetailSchema,
    adminUserSummarySchema,
    authTokenSchema,
    availableConnectorsSchema,
    budgetCellSchema,
    cancelledResponseSchema,
    connectionSchema,
    deletedCountResponseSchema,
    deletedResponseSchema,
    deltaResponseSchema,
    duplicatesResponseSchema,
    entitySchema,
    importPreviewSchema,
    importResultSchema,
    okResponseSchema,
    setResponseSchema,
    snapshotSchema,
    splitsResponseSchema,
    syncResultSchema,
    transactionPageSchema,
    transferDetectionResponseSchema,
    transferIdResponseSchema,
    transferSuggestionsResponseSchema,
    userSchema,
    workbookPreviewSchema,
    workbookResultSchema,
} from "./apiSchemas.js";

const tokenHeader = (): Record<string, string> => {
    const token = localStorage.getItem("monori_token");
    return token == null || token === "" ? {} : { Authorization: `Bearer ${token}` };
};

const apiFetch = (url: string, opts: RequestInit = {}) => {
    const headers = tokenHeader();
    if (opts.headers instanceof Headers) {
        for (const [name, value] of opts.headers.entries()) headers[name] = value;
    } else if (Array.isArray(opts.headers)) {
        for (const [name, value] of opts.headers) headers[name] = value;
    } else if (opts.headers != null) {
        Object.assign(headers, opts.headers);
    }
    return fetch(url, { ...opts, headers });
};

const json =
    <Schema extends z.ZodType>(schema: Schema) =>
    async (response: Response): Promise<z.output<Schema>> => {
        if (!response.ok) {
            if (
                response.status === 401 &&
                !response.url.includes("/api/auth/") &&
                localStorage.getItem("monori_token") != null &&
                localStorage.getItem("monori_token") !== ""
            ) {
                localStorage.removeItem("monori_token");
                window.location.replace("/login");
            }
            let detail = `${response.status} ${response.statusText}`;
            try {
                const body: unknown = await response.json();
                if (
                    typeof body === "object" &&
                    body !== null &&
                    "detail" in body &&
                    typeof body.detail === "string"
                ) {
                    detail = body.detail;
                }
            } catch {
                detail = `${response.status} ${response.statusText}`;
            }
            throw new Error(detail);
        }
        return schema.parse(await response.json());
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

async function copyBudgetYear(
    fromYear: number,
    toYear: number,
): Promise<{ copied: number; budgets: BudgetCell[] }> {
    return apiFetch("/api/budgets/copy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fromYear, toYear }),
    }).then(json(z.object({ copied: z.number(), budgets: z.array(budgetCellSchema) })));
}

export const api = {
    snapshot: ({
        light = false,
        limit,
    }: { light?: boolean; limit?: number } = {}): Promise<Snapshot> => {
        const qs = new URLSearchParams();
        if (light) qs.set("light", "1");
        if (limit != null) qs.set("limit", String(limit));
        const q = qs.toString();
        return apiFetch(`/api/snapshot${q === "" ? "" : `?${q}`}`).then(json(snapshotSchema));
    },
    transactions: ({
        limit = 1000,
        offset = 0,
    }: { limit?: number; offset?: number } = {}): Promise<TransactionPage> =>
        apiFetch(`/api/transactions?limit=${limit}&offset=${offset}`).then(
            json(transactionPageSchema),
        ),
    putBudget: (cell: BudgetCell): Promise<OkResponse> =>
        apiFetch("/api/budgets", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(cell),
        }).then(json(okResponseSchema)),
    copyBudgetYear,
    bulkBudgets: (cells: BudgetCell[]): Promise<OkResponse> =>
        apiFetch("/api/budgets/bulk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cells }),
        }).then(json(setResponseSchema)),
    hiddenTx: (offset = 0): Promise<TransactionPage> =>
        apiFetch(`/api/transactions?hidden=true&limit=1000&offset=${offset}`).then(
            json(transactionPageSchema),
        ),
    createTx: (body: TransactionCreate): Promise<IdResponse> =>
        apiFetch("/api/transactions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json(entitySchema)),
    patchTx: (id: Id, patch: TransactionPatch): Promise<OkResponse> =>
        apiFetch(`/api/transactions/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json(okResponseSchema)),
    replaceTxSplits: (id: Id, parts: Array<Omit<TransactionSplit, "id">>): Promise<SplitResponse> =>
        apiFetch(`/api/transactions/${id}/splits`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ parts }),
        }).then(json(splitsResponseSchema)),
    deleteTx: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/transactions/${id}`, { method: "DELETE" }).then(json(okResponseSchema)),
    createAccount: (body: AccountCreate): Promise<IdResponse> =>
        apiFetch("/api/accounts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json(entitySchema)),
    patchAccount: (id: Id, patch: AccountPatch): Promise<OkResponse> =>
        apiFetch(`/api/accounts/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json(okResponseSchema)),
    deleteAccount: (id: Id, reassignTo?: Id | null): Promise<OkResponse> =>
        apiFetch(`/api/accounts/${id}${reassignTo == null ? "" : `?reassignTo=${reassignTo}`}`, {
            method: "DELETE",
        }).then(json(okResponseSchema)),
    reorderAccounts: (ids: Id[]): Promise<void> =>
        apiFetch("/api/accounts/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        })
            .then(json(okResponseSchema))
            .then(() => undefined),
    reconcileAccount: (id: Id, actualBalance: number): Promise<{ delta: number }> =>
        apiFetch(`/api/accounts/${id}/reconcile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ actualBalance }),
        }).then(json(deltaResponseSchema)),
    createTransfer: (body: TransferCreate): Promise<TransferResponse> =>
        apiFetch("/api/transfers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json(transferIdResponseSchema)),
    // DELETE splits the transfer back into two ordinary transactions; the rows
    // are never removed, since half of them came from a bank
    splitTransfer: (transferId: string): Promise<OkResponse> =>
        apiFetch(`/api/transfers/${transferId}`, { method: "DELETE" }).then(json(okResponseSchema)),
    deleteTransferWithLegs: (transferId: string): Promise<{ deleted: number }> =>
        apiFetch(`/api/transfers/${transferId}/with-legs`, { method: "DELETE" }).then(
            json(deletedCountResponseSchema),
        ),
    linkTransfer: (body: TransferPair): Promise<TransferResponse> =>
        apiFetch("/api/transfers/link", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json(transferIdResponseSchema)),
    transferSuggestions: (): Promise<{ rows: TransferSuggestion[]; transactions: Transaction[] }> =>
        apiFetch("/api/transfers/suggestions").then(json(transferSuggestionsResponseSchema)),
    dismissTransferSuggestion: (body: TransferPair): Promise<OkResponse> =>
        apiFetch("/api/transfers/suggestions/dismiss", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json(okResponseSchema)),
    detectTransfers: (): Promise<{ merged: string[]; suggested: number }> =>
        apiFetch("/api/transfers/detect", { method: "POST" }).then(
            json(transferDetectionResponseSchema),
        ),
    createCategory: (body: CategoryCreate): Promise<IdResponse> =>
        apiFetch("/api/categories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json(entitySchema)),
    patchCategory: (id: Id, patch: CategoryPatch): Promise<OkResponse> =>
        apiFetch(`/api/categories/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json(okResponseSchema)),
    archiveGoal: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/categories/${id}/archive-goal`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        }).then(json(okResponseSchema)),
    deleteCategory: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/categories/${id}`, { method: "DELETE" }).then(json(okResponseSchema)),
    mergeCategory: (id: Id, into: Id): Promise<OkResponse> =>
        apiFetch(`/api/categories/${id}/merge`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ into }),
        }).then(json(okResponseSchema)),
    reorderCategories: (ids: Id[]): Promise<OkResponse> =>
        apiFetch("/api/categories/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json(okResponseSchema)),
    createGroup: (body: { name: string; kind: string }): Promise<IdResponse> =>
        apiFetch("/api/groups", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json(entitySchema)),
    patchGroup: (id: Id, patch: { name?: string; kind?: string }): Promise<OkResponse> =>
        apiFetch(`/api/groups/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json(okResponseSchema)),
    deleteGroup: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/groups/${id}`, { method: "DELETE" }).then(json(okResponseSchema)),
    reorderGroups: (ids: Id[]): Promise<OkResponse> =>
        apiFetch("/api/groups/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json(okResponseSchema)),
    importPreview: (text: string, accountId: Id | null = null): Promise<ImportPreview> =>
        apiFetch("/api/import/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, accountId }),
        }).then(json(importPreviewSchema)),
    importDuplicates: (
        rows: Array<Pick<ImportRow, "date" | "amount"> & Partial<ImportRow>>,
    ): Promise<{ duplicates: boolean[] }> =>
        apiFetch("/api/import/duplicates", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rows }),
        }).then(json(duplicatesResponseSchema)),
    importCommit: (
        rows: Array<Partial<ImportRow> & { id?: Id }>,
        accountId: Id | null = null,
    ): Promise<ImportResult> =>
        apiFetch("/api/import/commit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rows, accountId }),
        }).then(json(importResultSchema)),
    connectionsAvailable: (): Promise<AvailableConnector[]> =>
        apiFetch("/api/connections/available").then(json(availableConnectorsSchema)),
    createConnection: (body: {
        bank: string;
        kind: string;
        credentials: Record<string, string>;
    }): Promise<IdResponse> =>
        apiFetch("/api/connections", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json(connectionSchema)),
    deleteConnection: (id: Id): Promise<{ deleted: Id }> =>
        apiFetch(`/api/connections/${id}`, { method: "DELETE" }).then(json(deletedResponseSchema)),
    syncConnection: (id: Id): Promise<SyncResult> =>
        apiFetch(`/api/connections/${id}/sync`, { method: "POST" }).then(json(syncResultSchema)),
    submitConnectionSms: (id: Id, code: string): Promise<SyncResult> =>
        apiFetch(`/api/connections/${id}/sms`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code }),
        }).then(json(syncResultSchema)),
    cancelConnectionSync: (id: Id): Promise<{ cancelled: Id }> =>
        apiFetch(`/api/connections/${id}/cancel`, { method: "POST" }).then(
            json(cancelledResponseSchema),
        ),
    authRegister: (email: string, password: string): Promise<User> =>
        apiFetch("/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        }).then(json(userSchema)),
    authLogin: (email: string, password: string): Promise<{ access_token: string }> => {
        // OAuth2 password grant is form-encoded, username = email
        const form = new URLSearchParams();
        form.set("username", email);
        form.set("password", password);
        return apiFetch("/api/auth/token", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: form,
        }).then(json(authTokenSchema));
    },
    authMe: (token: string): Promise<User> =>
        apiFetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } }).then(
            json(userSchema),
        ),
    authPatchMe: (patch: Partial<Pick<User, "defaultAccountId">>): Promise<User> =>
        apiFetch("/api/auth/me", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json(userSchema)),
    exportXlsx: async () => {
        const r = await apiFetch("/api/export/xlsx");
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.blob();
    },
    workbookPreview: (file: File): Promise<WorkbookPreview> => {
        const form = new FormData();
        form.append("file", file);
        return apiFetch("/api/import/workbook/preview", { method: "POST", body: form }).then(
            json(workbookPreviewSchema),
        );
    },
    adminOverview: (): Promise<AdminOverview> =>
        apiFetch("/api/admin/overview").then(json(adminOverviewSchema)),
    adminUsers: (): Promise<AdminUserSummary[]> =>
        apiFetch("/api/admin/users").then(json(z.array(adminUserSummarySchema))),
    adminUserDetail: (id: Id): Promise<AdminUserDetail> =>
        apiFetch(`/api/admin/users/${id}`).then(json(adminUserDetailSchema)),
    adminUserTransactions: (
        id: Id,
        { limit = 1000, offset = 0 }: { limit?: number; offset?: number } = {},
    ): Promise<AdminTransaction[]> =>
        apiFetch(`/api/admin/users/${id}/transactions?limit=${limit}&offset=${offset}`).then(
            json(z.array(adminTransactionSchema)),
        ),
    adminDeleteUserTransactions: (id: Id, ids: Id[]): Promise<{ deleted: number }> =>
        apiFetch(`/api/admin/users/${id}/transactions/delete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json(deletedCountResponseSchema)),
    adminActivity: (): Promise<AdminActivity> =>
        apiFetch("/api/admin/activity").then(json(adminActivitySchema)),
    adminSql: (sql: string, confirmWrite = false, dryRun = false): Promise<AdminSqlResult> =>
        apiFetch("/api/admin/sql", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sql, confirmWrite, dryRun }),
        }).then(json(adminSqlResultSchema)),
    adminDeleteUser: (id: Id): Promise<OkResponse> =>
        apiFetch(`/api/admin/users/${id}`, { method: "DELETE" }).then(json(okResponseSchema)),
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
        return apiFetch("/api/import/workbook/commit", { method: "POST", body: form }).then(
            json(workbookResultSchema),
        );
    },
};
