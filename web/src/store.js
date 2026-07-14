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
      (b) => !(b.categoryId === categoryId && b.year === year && b.month === month),
    );
    if (amount !== 0) budgets.push({ categoryId, year, month, amount });
    set({ snapshot: { ...snapshot, budgets } });
    if (isDemo()) return;
    api
      .putBudget({ categoryId, year, month, amount })
      .catch((e) =>
        set({ toast: { title: "Failed to save budget", theme: "danger", content: String(e) } }),
      );
  },

  setTxCategory(txId, categoryId) {
    const { snapshot } = get();
    const transactions = snapshot.transactions.map((t) =>
      t.id === txId ? { ...t, categoryId } : t,
    );
    set({ snapshot: { ...snapshot, transactions } });
    if (isDemo()) return;
    api.patchTx(txId, { categoryId: categoryId ?? 0 }).catch((e) =>
      set({
        toast: { title: "Failed to update transaction", theme: "danger", content: String(e) },
      }),
    );
  },

  setTxAccount(txId, accountId) {
    const { snapshot } = get();
    const transactions = snapshot.transactions.map((t) =>
      t.id === txId ? { ...t, accountId } : t,
    );
    set({ snapshot: { ...snapshot, transactions } });
    if (isDemo()) return;
    api.patchTx(txId, { accountId }).catch((e) =>
      set({
        toast: { title: "Failed to move transaction", theme: "danger", content: String(e) },
      }),
    );
  },

  async createAccount(body) {
    const { snapshot } = get();
    const id = isDemo()
      ? Math.max(0, ...snapshot.accounts.map((a) => a.id)) + 1
      : (await api.createAccount(body)).id;
    const accounts = [
      ...snapshot.accounts,
      {
        id,
        name: body.name,
        type: body.type ?? "other",
        currency: body.currency ?? "RUB",
        sort: 1e9,
        archived: false,
        openingBalance: body.openingBalance ?? 0,
        openingDate: body.openingDate ?? null,
      },
    ];
    set({ snapshot: { ...snapshot, accounts } });
    return id;
  },

  async patchAccount(id, patch) {
    if (!isDemo()) await api.patchAccount(id, patch);
    const { snapshot } = get();
    const accounts = snapshot.accounts.map((a) => (a.id === id ? { ...a, ...patch } : a));
    set({ snapshot: { ...snapshot, accounts } });
  },

  async deleteAccount(id, reassignTo) {
    if (!isDemo()) await api.deleteAccount(id, reassignTo);
    const { snapshot } = get();
    set({
      snapshot: {
        ...snapshot,
        accounts: snapshot.accounts.filter((a) => a.id !== id),
        transactions: reassignTo
          ? snapshot.transactions.map((t) =>
              t.accountId === id ? { ...t, accountId: reassignTo } : t,
            )
          : snapshot.transactions,
      },
    });
  },

  async reconcileAccount(id, actualBalance) {
    if (isDemo()) {
      const { snapshot } = get();
      const balance = snapshot.accounts.find((a) => a.id === id)
        ? snapshot.transactions
            .filter((t) => t.accountId === id)
            .reduce(
              (s, t) => s + t.amount,
              snapshot.accounts.find((a) => a.id === id).openingBalance ?? 0,
            )
        : 0;
      const delta = actualBalance - balance;
      if (delta !== 0) {
        const nextId = Math.max(0, ...snapshot.transactions.map((t) => t.id)) + 1;
        const tx = {
          id: nextId,
          date: new Date().toISOString(),
          amount: delta,
          description: "Reconcile adjustment",
          bankCategory: "",
          mcc: "",
          categoryId: null,
          accountId: id,
          transferId: null,
          comment: "",
          source: "adjustment",
        };
        set({ snapshot: { ...snapshot, transactions: [...snapshot.transactions, tx] } });
      }
      return { delta };
    }
    const res = await api.reconcileAccount(id, actualBalance);
    await get().load();
    return res;
  },

  async createTransfer(body) {
    if (isDemo()) {
      const { snapshot } = get();
      const nextId = Math.max(0, ...snapshot.transactions.map((t) => t.id)) + 1;
      const transferId = `demo-${nextId}`;
      const rows = [
        { accountId: body.fromAccountId, amount: -body.amount },
        { accountId: body.toAccountId, amount: body.amount },
      ].map((r, i) => ({
        id: nextId + i,
        date: body.date,
        amount: r.amount,
        description: "Transfer",
        bankCategory: "",
        mcc: "",
        categoryId: null,
        accountId: r.accountId,
        transferId,
        comment: body.comment ?? "",
        source: "transfer",
      }));
      set({ snapshot: { ...snapshot, transactions: [...snapshot.transactions, ...rows] } });
      return transferId;
    }
    const { transferId } = await api.createTransfer(body);
    await get().load();
    return transferId;
  },

  async deleteTransfer(transferId) {
    if (!isDemo()) await api.deleteTransfer(transferId);
    const { snapshot } = get();
    set({
      snapshot: {
        ...snapshot,
        transactions: snapshot.transactions.filter((t) => t.transferId !== transferId),
      },
    });
  },

  async createCategory(body) {
    const { snapshot } = get();
    const id = isDemo()
      ? Math.max(0, ...snapshot.categories.map((c) => c.id)) + 1
      : (await api.createCategory(body)).id;
    const categories = [
      ...snapshot.categories,
      {
        id,
        groupId: body.groupId,
        name: body.name,
        keywords: body.keywords ?? "",
        sort: 1e9,
        archived: false,
      },
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
        : c,
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
          t.categoryId === id ? { ...t, categoryId: reassignTo ?? null } : t,
        ),
      },
    });
  },

  async commitImport(rows, accountId) {
    if (isDemo()) return { imported: 0, skipped: 0, demo: true };
    const res = await api.importCommit(rows, accountId);
    await get().load();
    return res;
  },
}));
