const json = (r) => {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
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
  importCommit: (rows) =>
    fetch("/api/import/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows }),
    }).then(json),
};
