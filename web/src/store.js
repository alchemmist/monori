import { create } from "zustand";
import { api } from "./api.js";
import { demoSnapshot } from "./demo/demoData.js";

/** The public /demo page runs entirely on the bundled sample dataset: no auth,
 * no backend calls. Mutations still work but stay local (nothing is persisted). */
export const isDemo = () => {
  if (typeof window === "undefined") return false;
  const p = window.location.pathname.replace(/\/+$/, "");
  return p === "/demo" || p.startsWith("/demo/");
};

export const useStore = create((set, get) => ({
  snapshot: null,
  loading: true,
  error: null,
  toast: null,

  async load() {
    if (isDemo()) {
      set({ snapshot: structuredClone(demoSnapshot), loading: false, error: null });
      return;
    }
    try {
      const snapshot = await api.snapshot();
      set({ snapshot, loading: false, error: null });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  notify(toast) {
    set({ toast });
  },

  /** Optimistic budget edit: local state changes instantly, server call follows. */
  setBudget(categoryId, year, month, amount) {
    const { snapshot } = get();
    const budgets = snapshot.budgets.filter(
      (b) => !(b.categoryId === categoryId && b.year === year && b.month === month)
    );
    if (amount !== 0) budgets.push({ categoryId, year, month, amount });
    set({ snapshot: { ...snapshot, budgets } });
    if (isDemo()) return;
    api.putBudget({ categoryId, year, month, amount }).catch((e) =>
      set({ toast: { title: "Failed to save budget", theme: "danger", content: String(e) } })
    );
  },

  setTxCategory(txId, categoryId) {
    const { snapshot } = get();
    const transactions = snapshot.transactions.map((t) =>
      t.id === txId ? { ...t, categoryId } : t
    );
    set({ snapshot: { ...snapshot, transactions } });
    if (isDemo()) return;
    api.patchTx(txId, { categoryId: categoryId ?? 0 }).catch((e) =>
      set({ toast: { title: "Failed to update transaction", theme: "danger", content: String(e) } })
    );
  },

  async createCategory(body) {
    const { snapshot } = get();
    const id = isDemo()
      ? Math.max(0, ...snapshot.categories.map((c) => c.id)) + 1
      : (await api.createCategory(body)).id;
    const categories = [
      ...snapshot.categories,
      { id, groupId: body.groupId, name: body.name, keywords: body.keywords ?? "", sort: 1e9, archived: false },
    ];
    set({ snapshot: { ...snapshot, categories } });
    return id;
  },

  async patchCategory(id, patch) {
    if (!isDemo()) await api.patchCategory(id, patch);
    const { snapshot } = get();
    const categories = snapshot.categories.map((c) =>
      c.id === id
        ? {
            ...c,
            ...(patch.name != null ? { name: patch.name } : {}),
            ...(patch.groupId != null ? { groupId: patch.groupId } : {}),
            ...(patch.keywords != null ? { keywords: patch.keywords } : {}),
          }
        : c
    );
    set({ snapshot: { ...snapshot, categories } });
  },

  async deleteCategory(id, reassignTo) {
    if (!isDemo()) await api.deleteCategory(id, reassignTo);
    const { snapshot } = get();
    set({
      snapshot: {
        ...snapshot,
        categories: snapshot.categories.filter((c) => c.id !== id),
        budgets: snapshot.budgets.filter((b) => b.categoryId !== id),
        transactions: snapshot.transactions.map((t) =>
          t.categoryId === id ? { ...t, categoryId: reassignTo ?? null } : t
        ),
      },
    });
  },

  async commitImport(rows) {
    if (isDemo()) return { imported: 0, skipped: 0, demo: true };
    const res = await api.importCommit(rows);
    await get().load();
    return res;
  },
}));
