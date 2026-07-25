const tokenHeader = () => {
    const token = localStorage.getItem("monori_token");
    return token ? { Authorization: `Bearer ${token}` } : {};
};

const apiFetch = (url, opts = {}) =>
    fetch(url, { ...opts, headers: { ...tokenHeader(), ...(opts.headers || {}) } });

const json = async (r) => {
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
            const body = await r.json();
            if (body?.detail) detail = body.detail;
        } catch {
            detail = `${r.status} ${r.statusText}`;
        }
        throw new Error(detail);
    }
    return r.json();
};

export const api = {
    snapshot: ({ light = false, limit } = {}) => {
        const qs = new URLSearchParams();
        if (light) qs.set("light", "1");
        if (limit) qs.set("limit", String(limit));
        const q = qs.toString();
        return apiFetch(`/api/snapshot${q ? `?${q}` : ""}`).then(json);
    },
    transactions: ({ limit = 1000, offset = 0 } = {}) =>
        apiFetch(`/api/transactions?limit=${limit}&offset=${offset}`).then(json),
    putBudget: (cell) =>
        apiFetch("/api/budgets", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(cell),
        }).then(json),
    bulkBudgets: (cells) =>
        apiFetch("/api/budgets/bulk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cells }),
        }).then(json),
    hiddenTx: (offset = 0) =>
        apiFetch(`/api/transactions?hidden=true&limit=1000&offset=${offset}`).then(json),
    patchTx: (id, patch) =>
        apiFetch(`/api/transactions/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    deleteTx: (id) => apiFetch(`/api/transactions/${id}`, { method: "DELETE" }).then(json),
    createAccount: (body) =>
        apiFetch("/api/accounts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    patchAccount: (id, patch) =>
        apiFetch(`/api/accounts/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    deleteAccount: (id, reassignTo) =>
        apiFetch(`/api/accounts/${id}${reassignTo ? `?reassignTo=${reassignTo}` : ""}`, {
            method: "DELETE",
        }).then(json),
    reorderAccounts: (ids) =>
        apiFetch("/api/accounts/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json),
    reconcileAccount: (id, actualBalance) =>
        apiFetch(`/api/accounts/${id}/reconcile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ actualBalance }),
        }).then(json),
    createTransfer: (body) =>
        apiFetch("/api/transfers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    // DELETE splits the transfer back into two ordinary transactions; the rows
    // are never removed, since half of them came from a bank
    splitTransfer: (transferId) =>
        apiFetch(`/api/transfers/${transferId}`, { method: "DELETE" }).then(json),
    linkTransfer: (body) =>
        apiFetch("/api/transfers/link", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    transferSuggestions: () => apiFetch("/api/transfers/suggestions").then(json),
    dismissTransferSuggestion: (body) =>
        apiFetch("/api/transfers/suggestions/dismiss", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    detectTransfers: () => apiFetch("/api/transfers/detect", { method: "POST" }).then(json),
    createCategory: (body) =>
        apiFetch("/api/categories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    patchCategory: (id, patch) =>
        apiFetch(`/api/categories/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    deleteCategory: (id) => apiFetch(`/api/categories/${id}`, { method: "DELETE" }).then(json),
    mergeCategory: (id, into) =>
        apiFetch(`/api/categories/${id}/merge`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ into }),
        }).then(json),
    reorderCategories: (ids) =>
        apiFetch("/api/categories/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json),
    createGroup: (body) =>
        apiFetch("/api/groups", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    patchGroup: (id, patch) =>
        apiFetch(`/api/groups/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    deleteGroup: (id) => apiFetch(`/api/groups/${id}`, { method: "DELETE" }).then(json),
    reorderGroups: (ids) =>
        apiFetch("/api/groups/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json),
    importPreview: (text, accountId) =>
        apiFetch("/api/import/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, accountId }),
        }).then(json),
    importCommit: (rows, accountId) =>
        apiFetch("/api/import/commit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ accountId, rows }),
        }).then(json),
    connectionsAvailable: () => apiFetch("/api/connections/available").then(json),
    createConnection: (body) =>
        apiFetch("/api/connections", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    deleteConnection: (id) => apiFetch(`/api/connections/${id}`, { method: "DELETE" }).then(json),
    syncConnection: (id) => apiFetch(`/api/connections/${id}/sync`, { method: "POST" }).then(json),
    submitConnectionSms: (id, code) =>
        apiFetch(`/api/connections/${id}/sms`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code }),
        }).then(json),
    cancelConnectionSync: (id) =>
        apiFetch(`/api/connections/${id}/cancel`, { method: "POST" }).then(json),
    authRegister: (email, password) =>
        apiFetch("/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        }).then(json),
    authLogin: (email, password) => {
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
    authMe: (token) =>
        apiFetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } }).then(json),
    exportXlsx: async () => {
        const r = await apiFetch("/api/export/xlsx");
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.blob();
    },
    workbookPreview: (file) => {
        const form = new FormData();
        form.append("file", file);
        return apiFetch("/api/import/workbook/preview", { method: "POST", body: form }).then(json);
    },
    adminOverview: () => apiFetch("/api/admin/overview").then(json),
    adminUsers: () => apiFetch("/api/admin/users").then(json),
    adminUserDetail: (id) => apiFetch(`/api/admin/users/${id}`).then(json),
    adminUserTransactions: (id, { limit = 1000, offset = 0 } = {}) =>
        apiFetch(`/api/admin/users/${id}/transactions?limit=${limit}&offset=${offset}`).then(json),
    adminDeleteUserTransactions: (id, ids) =>
        apiFetch(`/api/admin/users/${id}/transactions/delete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json),
    adminActivity: () => apiFetch("/api/admin/activity").then(json),
    adminSql: (sql, confirmWrite = false, dryRun = false) =>
        apiFetch("/api/admin/sql", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sql, confirmWrite, dryRun }),
        }).then(json),
    adminDeleteUser: (id) => apiFetch(`/api/admin/users/${id}`, { method: "DELETE" }).then(json),
    workbookCommit: (file, mapping, budgetPolicy) => {
        const form = new FormData();
        form.append("file", file);
        form.append("mapping", JSON.stringify(mapping));
        form.append("budgetPolicy", budgetPolicy);
        return apiFetch("/api/import/workbook/commit", { method: "POST", body: form }).then(json);
    },
};
