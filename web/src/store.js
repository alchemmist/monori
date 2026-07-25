import { create } from "zustand";
import { api } from "./api.js";
import { demoSnapshot } from "./demo/demoData.js";
import { mergeTransactions } from "./mergeTransactions.js";

/** Rows per background chunk once the light snapshot has painted. */
export const TX_CHUNK = 1000;

/** How long chunks are allowed to pile up before they land in the snapshot.
 * Every snapshot write re-runs the budget/dashboard math over the whole ledger,
 * so on a fast link the chunks are coalesced instead of recomputing per chunk. */
export const TX_FLUSH_MS = 250;

/** Bumped by every load(); a fill whose generation is stale drops its results. */
let fillGeneration = 0;

const now = () => (typeof performance !== "undefined" ? performance.now() : 0);

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
    /** `{loaded, total}` while the background fill runs, null when it's done. */
    txProgress: null,
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

    /**
     * First paint waits only on the light snapshot — everything but the bulk of
     * the ledger, plus its newest page. The rest streams in behind it.
     */
    async load() {
        // claimed before the await, so two overlapping loads (React StrictMode
        // remounts, a reload during a fill) leave only the last one filling
        const generation = (fillGeneration += 1);
        if (isDemo()) {
            const snapshot = structuredClone(demoSnapshot);
            set({
                snapshot: { ...snapshot, transactionsTotal: snapshot.transactions.length },
                loading: false,
                error: null,
                txProgress: null,
            });
            return;
        }
        try {
            const snapshot = await api.snapshot({ light: true });
            if (generation !== fillGeneration) return;
            set({ snapshot, loading: false, error: null });
        } catch (e) {
            set({ error: String(e), loading: false, txProgress: null });
            return;
        }
        get().fillTransactions(generation);
    },

    /**
     * Pull the transactions the light snapshot left out, oldest-remaining first,
     * merging each chunk into the canonical order so derived views just
     * recompute. Offsets count back from the newest row: a local insert during
     * the fill can shift them, and the id-dedupe in the merge absorbs that.
     */
    async fillTransactions(generation = fillGeneration) {
        const snapshot = get().snapshot;
        if (!snapshot) return;
        let offset = snapshot.transactions.length;
        let total = snapshot.transactionsTotal ?? offset;
        if (offset >= total) {
            set({ txProgress: null });
            return;
        }
        set({ txProgress: { loaded: offset, total } });
        // chunks wait here until a flush, so a fast link doesn't re-run the
        // derived math once per chunk
        let pending = [];
        let flushedAt = now();
        const flush = (done) => {
            const current = get().snapshot;
            const transactions = mergeTransactions(current.transactions, pending);
            pending = [];
            flushedAt = now();
            set({
                snapshot: {
                    ...current,
                    transactions,
                    transactionsTotal: Math.max(total, transactions.length),
                },
                txProgress: done ? null : { loaded: transactions.length, total },
            });
        };
        try {
            for (;;) {
                const page = await api.transactions({ limit: TX_CHUNK, offset });
                if (generation !== fillGeneration) return;
                offset += page.rows.length;
                total = Math.max(page.total, offset);
                pending = mergeTransactions(pending, [...page.rows].reverse());
                const loaded = get().snapshot.transactions.length + pending.length;
                const done = page.rows.length < TX_CHUNK || loaded >= total;
                if (done || now() - flushedAt >= TX_FLUSH_MS) flush(done);
                else set({ txProgress: { loaded, total } });
                if (done) return;
            }
        } catch (e) {
            if (generation !== fillGeneration) return;
            set({ txProgress: null });
            get().notify({
                title: "Failed to load older transactions",
                theme: "danger",
                content: String(e),
            });
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

    /** Kanban drop: move a card to `toGroupId` and lay out every category by the
     *  global order in `orderedIds` (assigns 1..N to sort). Optimistic; the group
     *  change and the reorder are both persisted, then resynced on failure. */
    async moveCategory(id, toGroupId, orderedIds) {
        const { snapshot } = get();
        const cat = snapshot.categories.find((c) => c.id === id);
        const groupChanged = cat && cat.groupId !== toGroupId;
        const sortById = new Map(orderedIds.map((cid, i) => [cid, i + 1]));
        const categories = snapshot.categories.map((c) => ({
            ...c,
            groupId: c.id === id ? toGroupId : c.groupId,
            sort: sortById.get(c.id) ?? c.sort,
        }));
        set({ snapshot: { ...snapshot, categories } });
        if (isDemo()) return;
        try {
            if (groupChanged) await api.patchCategory(id, { groupId: toGroupId });
            await api.reorderCategories(orderedIds);
        } catch (e) {
            get().notify({ title: "Failed to move category", theme: "danger", content: String(e) });
            await get().load();
        }
    },

    async createGroup(body) {
        const { snapshot } = get();
        const id = isDemo()
            ? Math.max(0, ...snapshot.groups.map((g) => g.id)) + 1
            : (await api.createGroup(body)).id;
        const groups = [...snapshot.groups, { id, name: body.name, kind: body.kind, sort: 1e9 }];
        set({ snapshot: { ...snapshot, groups } });
        return id;
    },

    async patchGroup(id, patch) {
        if (!isDemo()) await api.patchGroup(id, patch);
        const { snapshot } = get();
        const groups = snapshot.groups.map((g) => (g.id === id ? { ...g, ...patch } : g));
        set({ snapshot: { ...snapshot, groups } });
    },

    async deleteGroup(id) {
        if (!isDemo()) await api.deleteGroup(id);
        const { snapshot } = get();
        set({ snapshot: { ...snapshot, groups: snapshot.groups.filter((g) => g.id !== id) } });
    },

    async reorderGroups(orderedIds) {
        const { snapshot } = get();
        const sortById = new Map(orderedIds.map((gid, i) => [gid, i + 1]));
        const groups = snapshot.groups.map((g) => ({ ...g, sort: sortById.get(g.id) ?? g.sort }));
        set({ snapshot: { ...snapshot, groups } });
        if (isDemo()) return;
        api.reorderGroups(orderedIds).catch(async (e) => {
            get().notify({
                title: "Failed to reorder groups",
                theme: "danger",
                content: String(e),
            });
            await get().load();
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
