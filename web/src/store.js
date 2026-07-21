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
    user: null,
    authChecked: false,

    async checkAuth() {
        if (isDemo()) {
            set({ authChecked: true });
            return;
        }
        const token = localStorage.getItem("monori_token");
        if (!token) {
            set({ authChecked: true });
            return;
        }
        try {
            const user = await api.authMe(token);
            set({ user, authChecked: true });
        } catch {
            localStorage.removeItem("monori_token");
            set({ user: null, authChecked: true });
        }
    },

    async login(email, password) {
        const { access_token } = await api.authLogin(email, password);
        localStorage.setItem("monori_token", access_token);
        const user = await api.authMe(access_token);
        set({ user });
    },

    async register(email, password) {
        await api.authRegister(email, password);
        await get().login(email, password);
    },

    logout() {
        localStorage.removeItem("monori_token");
        set({ user: null });
    },

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
        api.putBudget({ categoryId, year, month, amount }).catch((e) =>
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
                toast: {
                    title: "Failed to update transaction",
                    theme: "danger",
                    content: String(e),
                },
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
                icon: body.icon ?? "wallet",
                color: body.color ?? "#5b6472",
                iconImage: body.iconImage || null,
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
                    date: new Date().toISOString().slice(0, 19),
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
                      ...(patch.archived != null ? { archived: patch.archived } : {}),
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

    async createConnection(body) {
        if (isDemo()) throw new Error("Bank sync is not available in the demo");
        const conn = await api.createConnection(body);
        await get().load();
        return conn;
    },

    async deleteConnection(id) {
        if (isDemo()) return;
        await api.deleteConnection(id);
        await get().load();
    },

    async syncConnection(id) {
        if (isDemo()) throw new Error("Bank sync is not available in the demo");
        const res = await api.syncConnection(id);
        await get().load();
        return res;
    },

    async submitConnectionSms(id, code) {
        if (isDemo()) throw new Error("Bank sync is not available in the demo");
        const res = await api.submitConnectionSms(id, code);
        await get().load();
        return res;
    },

    async cancelConnectionSync(id) {
        if (isDemo()) return;
        await api.cancelConnectionSync(id);
        await get().load();
    },
}));
