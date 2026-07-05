import { create } from "zustand";
import { api } from "./api.js";

export const useStore = create((set, get) => ({
  snapshot: null,
  loading: true,
  error: null,
  toast: null,

  async load() {
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
    api.patchTx(txId, { categoryId: categoryId ?? 0 }).catch((e) =>
      set({ toast: { title: "Failed to update transaction", theme: "danger", content: String(e) } })
    );
  },

  async createCategory(body) {
    const { id } = await api.createCategory(body);
    const { snapshot } = get();
    const categories = [
      ...snapshot.categories,
      { id, groupId: body.groupId, name: body.name, keywords: body.keywords ?? "", sort: 1e9, archived: false },
    ];
    set({ snapshot: { ...snapshot, categories } });
    return id;
  },

  async patchCategory(id, patch) {
    await api.patchCategory(id, patch);
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
    await api.deleteCategory(id, reassignTo);
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
    const res = await api.importCommit(rows);
    await get().load();
    return res;
  },
}));
