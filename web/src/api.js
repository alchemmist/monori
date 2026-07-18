const json = async (r) => {
    if (!r.ok) {
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
    snapshot: () => fetch("/api/snapshot").then(json),
    putBudget: (cell) =>
        fetch("/api/budgets", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(cell),
        }).then(json),
    patchTx: (id, patch) =>
        fetch(`/api/transactions/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    deleteTx: (id) => fetch(`/api/transactions/${id}`, { method: "DELETE" }).then(json),
    createAccount: (body) =>
        fetch("/api/accounts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    patchAccount: (id, patch) =>
        fetch(`/api/accounts/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    deleteAccount: (id, reassignTo) =>
        fetch(`/api/accounts/${id}${reassignTo ? `?reassignTo=${reassignTo}` : ""}`, {
            method: "DELETE",
        }).then(json),
    reorderAccounts: (ids) =>
        fetch("/api/accounts/reorder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids }),
        }).then(json),
    reconcileAccount: (id, actualBalance) =>
        fetch(`/api/accounts/${id}/reconcile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ actualBalance }),
        }).then(json),
    createTransfer: (body) =>
        fetch("/api/transfers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    deleteTransfer: (transferId) =>
        fetch(`/api/transfers/${transferId}`, { method: "DELETE" }).then(json),
    createCategory: (body) =>
        fetch("/api/categories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    patchCategory: (id, patch) =>
        fetch(`/api/categories/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(patch),
        }).then(json),
    deleteCategory: (id, reassignTo) =>
        fetch(`/api/categories/${id}${reassignTo ? `?reassignTo=${reassignTo}` : ""}`, {
            method: "DELETE",
        }).then(json),
    importPreview: (text) =>
        fetch("/api/import/preview", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        }).then(json),
    importCommit: (rows, accountId) =>
        fetch("/api/import/commit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ accountId, rows }),
        }).then(json),
    createConnection: (body) =>
        fetch("/api/connections", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        }).then(json),
    deleteConnection: (id) => fetch(`/api/connections/${id}`, { method: "DELETE" }).then(json),
    syncConnection: (id) => fetch(`/api/connections/${id}/sync`, { method: "POST" }).then(json),
    submitConnectionSms: (id, code) =>
        fetch(`/api/connections/${id}/sms`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code }),
        }).then(json),
};
