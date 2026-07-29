import { create } from "zustand";
import { api } from "./api.js";
import { demoSnapshot } from "./demo/demoData.js";
import { mergeCategories } from "./mergeCategories.js";
import { compareTx, mergeTransactions } from "./mergeTransactions.js";
import { loadTabs, saveTabs } from "./ui/tabPersist.js";

/** Rows per background chunk once the light snapshot has painted. */
export const TX_CHUNK = 1000;

/** How long chunks are allowed to pile up before they land in the snapshot.
 * Every snapshot write re-runs the budget/dashboard math over the whole ledger,
 * so on a fast link the chunks are coalesced instead of recomputing per chunk. */
export const TX_FLUSH_MS = 250;

/** Bumped by every load(); a fill whose generation is stale drops its results. */
let fillGeneration = 0;

/** Bumped by every hide/unhide, so an in-flight hidden-list fetch can tell it
 * is stale and must not overwrite the newer optimistic state. */
let hiddenEpoch = 0;

/** Rapid hide→unhide on one row must reach the server in order, or the earlier
 * PATCH could land last and win — so per-transaction PATCHes are chained. */
const txPatchChain = new Map();
function chainedPatchTx(id, patch) {
    const prev = txPatchChain.get(id) ?? Promise.resolve();
    const next = prev.catch(() => {}).then(() => api.patchTx(id, patch));
    txPatchChain.set(id, next);
    next.catch(() => {}).finally(() => {
        if (txPatchChain.get(id) === next) txPatchChain.delete(id);
    });
    return next;
}

/** Budget edits are persisted in order. Year copying waits for this chain so
 * the server always copies the latest values visible in the grid. */
let budgetWriteChain = null;
function chainedBudgetWrite(write) {
    let next;
    if (budgetWriteChain) {
        next = budgetWriteChain.catch(() => {}).then(write);
    } else {
        try {
            next = Promise.resolve(write());
        } catch (error) {
            next = Promise.reject(error);
        }
    }
    budgetWriteChain = next;
    return next;
}

// Each optimistic transaction edit owns revisions for the fields it changes.
// A failed older request must never undo a newer edit to the same field.
let nextTxFieldRevision = 0;
const txFieldRevisions = new Map();

let nextSplitRevision = 0;
const splitRevisions = new Map();

const now = () => (typeof performance !== "undefined" ? performance.now() : 0);

/** The public /demo page runs entirely on the bundled sample dataset: no auth,
 * no backend calls. Mutations still work but stay local (nothing is persisted). */
export const isDemo = () => {
    if (typeof window === "undefined") return false;
    const p = window.location.pathname.replace(/\/+$/, "");
    return p === "/demo" || p.startsWith("/demo/");
};

const restoredTabs = loadTabs();

// carries on past the restored ids, so a reopened tab never collides with one
// that came back from storage
let nextTabId = restoredTabs.reduce((max, t) => Math.max(max, t.id), 0) + 1;

export const useStore = create((set, get) => ({
    snapshot: null,
    loading: true,
    /** `{loaded, total}` while the background fill runs, null when it's done. */
    txProgress: null,
    error: null,
    toast: null,
    user: null,
    authChecked: false,

    // globally mounted side tabs (see TabHost): they belong to the app shell,
    // not a page, so navigating inside monori never closes them — and they are
    // mirrored into localStorage here, so a reload brings them back too
    tabs: restoredTabs,
    setTabs(tabs) {
        saveTabs(tabs);
        set({ tabs });
    },
    openTab(kind, props = {}, key = null) {
        const tabs = get().tabs;
        if (key != null && tabs.some((t) => t.key === key)) return;
        get().setTabs([...tabs, { id: nextTabId++, key, kind, props }]);
    },
    closeTab(id) {
        get().setTabs(get().tabs.filter((t) => t.id !== id));
    },
    closeTabByKey(key) {
        get().setTabs(get().tabs.filter((t) => t.key !== key));
    },

    // bumped by tabs that mutate admin data; the Admin page re-fetches while
    // mounted instead of holding a page callback inside persistent tab props
    adminTick: 0,
    bumpAdminTick() {
        set({ adminTick: get().adminTick + 1 });
    },

    async checkAuth() {
        if (isDemo()) {
            set({ authChecked: true });
            return;
        }
        const token = localStorage.getItem("monori_token");
        if (!token) {
            // no session — drop any restored tabs so they cannot resurface for
            // whoever signs in on this browser next
            get().setTabs([]);
            set({ authChecked: true });
            return;
        }
        try {
            const user = await api.authMe(token);
            set({ user, authChecked: true });
        } catch {
            localStorage.removeItem("monori_token");
            get().setTabs([]);
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

    async patchMe(patch) {
        const user = await api.authPatchMe(patch);
        set({ user });
        return user;
    },

    logout() {
        localStorage.removeItem("monori_token");
        get().setTabs([]);
        set({ user: null, hiddenTx: null });
    },

    /**
     * First paint waits only on the light snapshot — everything but the bulk of
     * the ledger, plus its newest page. The rest streams in behind it.
     */
    async load() {
        // claimed before the await, so two overlapping loads (React StrictMode
        // remounts, a reload during a fill) leave only the last one filling
        const generation = (fillGeneration += 1);
        // Do not briefly render a prior account's hidden ledger while the new
        // snapshot is loading. The epoch also discards any old hidden request.
        const reloadHidden = get().hiddenTx !== null;
        hiddenEpoch += 1;
        set({ hiddenTx: null });
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
        if (reloadHidden) get().loadHiddenTx();
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
            const currentTotal = current.transactionsTotal ?? current.transactions.length;
            const nextTotal = Math.max(total, currentTotal, transactions.length);
            pending = [];
            flushedAt = now();
            set({
                snapshot: {
                    ...current,
                    transactions,
                    transactionsTotal: nextTotal,
                },
                txProgress: done ? null : { loaded: transactions.length, total: nextTotal },
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
        if (isDemo()) return Promise.resolve();
        const write = chainedBudgetWrite(() => api.putBudget({ categoryId, year, month, amount }));
        write.catch((e) =>
            set({ toast: { title: "Failed to save budget", theme: "danger", content: String(e) } }),
        );
        return write;
    },

    /** Copy one category's current month into every later month of the year.
     * Unlike a display-only fill, this is one bulk request, so the resulting
     * plan is persisted atomically before the grid updates. */
    async fillBudgetForward(categoryId, year, month) {
        const { snapshot } = get();
        const amount =
            snapshot.budgets.find(
                (b) => b.categoryId === categoryId && b.year === year && b.month === month,
            )?.amount ?? 0;
        const cells = Array.from({ length: 12 - month }, (_, i) => ({
            categoryId,
            year,
            month: month + i + 1,
            amount,
        }));
        if (!cells.length) return 0;
        if (!isDemo()) await api.bulkBudgets(cells);

        const targetMonths = new Set(cells.map((cell) => cell.month));
        const budgets = snapshot.budgets.filter(
            (b) => b.categoryId !== categoryId || b.year !== year || !targetMonths.has(b.month),
        );
        if (amount !== 0) budgets.push(...cells);
        set({ snapshot: { ...snapshot, budgets } });
        return cells.length;
    },

    /** Persist an explicit set of ordinary budget cells atomically. */
    async setBudgets(cells) {
        if (!cells.length) return;
        if (!isDemo()) await api.bulkBudgets(cells);
        const { snapshot } = get();
        const keys = new Set(cells.map((c) => `${c.categoryId}-${c.year}-${c.month}`));
        const budgets = snapshot.budgets.filter(
            (b) => !keys.has(`${b.categoryId}-${b.year}-${b.month}`),
        );
        budgets.push(...cells.filter((c) => c.amount !== 0));
        set({ snapshot: { ...snapshot, budgets } });
    },

    /** Create a new planning year as an exact copy of the preceding year. */
    async copyBudgetYear(fromYear, toYear) {
        let copied;
        let targetBudgets;
        if (isDemo()) {
            targetBudgets = get()
                .snapshot.budgets.filter((b) => b.year === fromYear)
                .map((b) => ({ ...b, year: toYear }));
            copied = targetBudgets.length;
        } else {
            const precedingWrites = budgetWriteChain;
            try {
                if (precedingWrites) await precedingWrites;
            } catch (error) {
                if (budgetWriteChain === precedingWrites) budgetWriteChain = null;
                throw error;
            }
            const response = await api.copyBudgetYear(fromYear, toYear);
            copied = response.copied;
            targetBudgets = response.budgets;
        }
        const { snapshot } = get();
        const budgets = snapshot.budgets.filter((b) => b.year !== toYear);
        budgets.push(...targetBudgets);
        set({ snapshot: { ...snapshot, budgets } });
        return copied;
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

    /** Record a transaction by hand. The row is merged straight into the loaded
     * ledger instead of reloading the whole snapshot, so entering a run of them
     * one after another never blanks the page or loses the scroll position —
     * every derived view (budget, analytics, balances) recomputes from the
     * snapshot anyway. Returns the created row. */
    async addTransaction(body) {
        const { snapshot } = get();
        const row = {
            date: body.date,
            amount: body.amount,
            description: body.description ?? "",
            bankCategory: "",
            mcc: "",
            categoryId: body.categoryId ?? null,
            accountId: body.accountId,
            transferId: null,
            comment: body.comment ?? "",
            source: "manual",
        };
        let id;
        if (isDemo()) {
            id = Math.max(0, ...snapshot.transactions.map((t) => t.id)) + 1;
        } else {
            ({ id } = await api.createTx(body));
        }
        const tx = { ...row, id };
        const current = get().snapshot;
        set({
            snapshot: {
                ...current,
                transactions: mergeTransactions(current.transactions, [tx]),
                transactionsTotal: (current.transactionsTotal ?? current.transactions.length) + 1,
            },
        });
        // Creating a row shifts every older-page offset. Restart the fill so
        // its captured total and offsets cannot overwrite or skip this insert.
        if (get().txProgress) get().fillTransactions((fillGeneration += 1));
        return tx;
    },

    /** Edit a transaction's own fields — date, description, amount, comment.
     * Optimistic like every other ledger edit, but a failed save rolls the row
     * back: unlike a category, a wrong amount would keep every balance and
     * budget on the page lying until the next reload. A changed date moves the
     * row, so the ledger is re-sorted into canonical order. */
    async updateTransaction(txId, patch) {
        const { snapshot } = get();
        const before = snapshot.transactions.find((t) => t.id === txId);
        if (!before) return;
        const revision = (nextTxFieldRevision += 1);
        const revisions = txFieldRevisions.get(txId) ?? new Map();
        Object.keys(patch).forEach((key) => revisions.set(key, revision));
        txFieldRevisions.set(txId, revisions);
        const rows = snapshot.transactions.map((t) => (t.id === txId ? { ...t, ...patch } : t));
        if (patch.date !== undefined && patch.date !== before.date) rows.sort(compareTx);
        set({ snapshot: { ...snapshot, transactions: rows } });
        if (isDemo()) return;
        try {
            await api.patchTx(txId, patch);
        } catch (e) {
            const cur = get().snapshot;
            const undo = Object.fromEntries(
                Object.keys(patch)
                    .filter((key) => revisions.get(key) === revision)
                    .map((key) => [key, before[key]]),
            );
            const back = cur.transactions
                .map((t) => (t.id === txId ? { ...t, ...undo } : t))
                .sort(compareTx);
            set({
                snapshot: { ...cur, transactions: back },
                toast: {
                    title: "Failed to update transaction",
                    theme: "danger",
                    content: String(e),
                },
            });
        } finally {
            Object.keys(patch).forEach((key) => {
                if (revisions.get(key) === revision) revisions.delete(key);
            });
            if (!revisions.size) txFieldRevisions.delete(txId);
        }
    },

    async replaceTransactionSplits(txId, parts) {
        const { snapshot } = get();
        const before = snapshot.transactions.find((transaction) => transaction.id === txId);
        if (!before) return;
        const optimistic = parts.map((part, index) => ({ id: `new-${index}`, ...part }));
        const update = (splits) =>
            snapshot.transactions.map((transaction) =>
                transaction.id === txId
                    ? {
                          ...transaction,
                          categoryId: splits.length ? null : transaction.categoryId,
                          splits,
                      }
                    : transaction,
            );
        set({ snapshot: { ...snapshot, transactions: update(optimistic) } });
        if (isDemo()) return optimistic;
        const revision = ++nextSplitRevision;
        splitRevisions.set(txId, revision);
        try {
            const result = await api.replaceTxSplits(txId, parts);
            if (splitRevisions.get(txId) !== revision) return result.splits;
            const current = get().snapshot;
            set({
                snapshot: {
                    ...current,
                    transactions: current.transactions.map((transaction) =>
                        transaction.id === txId
                            ? {
                                  ...transaction,
                                  categoryId: result.splits.length ? null : transaction.categoryId,
                                  splits: result.splits,
                              }
                            : transaction,
                    ),
                },
            });
            return result.splits;
        } catch (error) {
            if (splitRevisions.get(txId) === revision) {
                const current = get().snapshot;
                set({
                    snapshot: {
                        ...current,
                        transactions: current.transactions.map((transaction) =>
                            transaction.id === txId
                                ? {
                                      ...transaction,
                                      categoryId: before.categoryId,
                                      splits: before.splits ?? [],
                                  }
                                : transaction,
                        ),
                    },
                });
            }
            throw error;
        } finally {
            if (splitRevisions.get(txId) === revision) splitRevisions.delete(txId);
        }
    },

    /** Delete a transaction for good. Also rolls back on failure, for the same
     * reason: a row that vanished from the ledger but not from the server would
     * quietly skew every total until a reload brought it back. */
    async deleteTransaction(txId) {
        const { snapshot } = get();
        const gone = snapshot.transactions.find((t) => t.id === txId);
        if (!gone) return false;
        set({
            snapshot: {
                ...snapshot,
                transactions: snapshot.transactions.filter((t) => t.id !== txId),
                transactionsTotal: Math.max(0, (snapshot.transactionsTotal ?? 1) - 1),
            },
        });
        if (isDemo()) return true;
        try {
            await api.deleteTx(txId);
            return true;
        } catch (e) {
            const cur = get().snapshot;
            set({
                snapshot: {
                    ...cur,
                    transactions: mergeTransactions(cur.transactions, [gone]),
                    transactionsTotal: (cur.transactionsTotal ?? 0) + 1,
                },
                toast: {
                    title: "Failed to delete transaction",
                    theme: "danger",
                    content: String(e),
                },
            });
            return false;
        }
    },

    /** Hidden transactions live outside the snapshot on purpose: nothing in
     * the app (budgets, analytics, balances) can see them by accident. null
     * until the transactions page first asks for them. */
    hiddenTx: null,

    async loadHiddenTx() {
        if (isDemo()) {
            if (!get().hiddenTx) set({ hiddenTx: [] });
            return;
        }
        const epoch = hiddenEpoch;
        try {
            const rows = [];
            for (;;) {
                const page = await api.hiddenTx(rows.length);
                if (epoch !== hiddenEpoch) return;
                rows.push(...page.rows);
                if (rows.length >= page.total || page.rows.length === 0) break;
            }
            set({ hiddenTx: rows.sort(compareTx) });
        } catch (e) {
            set({
                toast: {
                    title: "Failed to load hidden transactions",
                    theme: "danger",
                    content: String(e),
                },
            });
        }
    },

    hideTx(txId) {
        const { snapshot, hiddenTx } = get();
        const t = snapshot.transactions.find((x) => x.id === txId);
        if (!t) return;
        set({
            snapshot: {
                ...snapshot,
                transactions: snapshot.transactions.filter((x) => x.id !== txId),
                transactionsTotal: Math.max(0, (snapshot.transactionsTotal ?? 1) - 1),
            },
            hiddenTx: [...(hiddenTx ?? []), { ...t, hidden: true }].sort(compareTx),
        });
        if (isDemo()) return;
        hiddenEpoch += 1;
        chainedPatchTx(txId, { hidden: true }).then(
            () => {
                // once the server excludes this row, every list offset past it
                // shifts down by one — a running background fill would skip
                // the row that slid into its boundary, so restart it
                if (get().txProgress) get().fillTransactions((fillGeneration += 1));
            },
            (e) =>
                set({
                    toast: {
                        title: "Failed to hide transaction",
                        theme: "danger",
                        content: String(e),
                    },
                }),
        );
    },

    unhideTx(txId) {
        const { snapshot, hiddenTx } = get();
        const t = (hiddenTx ?? []).find((x) => x.id === txId);
        if (!t) return;
        set({
            snapshot: {
                ...snapshot,
                transactions: mergeTransactions(snapshot.transactions, [{ ...t, hidden: false }]),
                transactionsTotal: (snapshot.transactionsTotal ?? 0) + 1,
            },
            hiddenTx: hiddenTx.filter((x) => x.id !== txId),
        });
        if (isDemo()) return;
        hiddenEpoch += 1;
        chainedPatchTx(txId, { hidden: false }).catch((e) =>
            set({
                toast: {
                    title: "Failed to unhide transaction",
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
            const entity = {
                id: transferId,
                outTxId: rows[0].id,
                inTxId: rows[1].id,
                origin: "manual",
                note: body.comment ?? "",
                createdAt: body.date,
            };
            set({
                snapshot: {
                    ...snapshot,
                    transactions: [...snapshot.transactions, ...rows],
                    transfers: [...(snapshot.transfers ?? []), entity],
                },
            });
            return transferId;
        }
        const { transferId } = await api.createTransfer(body);
        await get().load();
        return transferId;
    },

    /** Merge two transactions the ledger already holds. Both rows stay exactly
     * as they are — only the link is new — so the next bank sync still
     * recognizes them and cannot bring in a duplicate. */
    async linkTransfer(outTxId, inTxId) {
        if (isDemo()) {
            const { snapshot } = get();
            const transferId = `demo-link-${outTxId}-${inTxId}`;
            set({
                snapshot: {
                    ...snapshot,
                    transactions: snapshot.transactions.map((t) =>
                        t.id === outTxId || t.id === inTxId
                            ? { ...t, transferId, categoryId: null }
                            : t,
                    ),
                    transfers: [
                        ...(snapshot.transfers ?? []),
                        { id: transferId, outTxId, inTxId, origin: "manual", note: "" },
                    ],
                },
            });
            return transferId;
        }
        const { transferId } = await api.linkTransfer({ outTxId, inTxId });
        await get().load();
        return transferId;
    },

    /** Split a transfer back into two ordinary transactions. Nothing is
     * deleted: to remove the money as well, delete the two rows afterwards. */
    async splitTransfer(transferId) {
        if (!isDemo()) {
            await api.splitTransfer(transferId);
            await get().load();
            return;
        }
        const { snapshot } = get();
        set({
            snapshot: {
                ...snapshot,
                transactions: snapshot.transactions.map((t) =>
                    t.transferId === transferId ? { ...t, transferId: null } : t,
                ),
                transfers: (snapshot.transfers ?? []).filter((x) => x.id !== transferId),
            },
        });
    },

    /** Split, then delete both rows — the one path that really removes the
     * money. Kept separate from splitTransfer so nothing can destroy a bank's
     * own transactions by accident. */
    async deleteTransferWithLegs(transferId) {
        const ids = get()
            .snapshot.transactions.filter((t) => t.transferId === transferId)
            .map((t) => t.id);
        if (!isDemo()) {
            await api.splitTransfer(transferId);
            await Promise.all(ids.map((id) => api.deleteTx(id)));
        }
        const { snapshot } = get();
        set({
            snapshot: {
                ...snapshot,
                transactions: snapshot.transactions.filter((t) => !ids.includes(t.id)),
                transfers: (snapshot.transfers ?? []).filter((x) => x.id !== transferId),
            },
        });
    },

    /** Pairs the server thinks are transfers but is not sure enough to merge
     * unasked. Detection lives on the server so the rule has exactly one
     * implementation; the demo dataset ships its transfers already merged. */
    async transferSuggestions() {
        if (isDemo()) return { rows: [], transactions: [] };
        return api.transferSuggestions();
    },

    async dismissTransferSuggestion(outTxId, inTxId) {
        if (isDemo()) return;
        await api.dismissTransferSuggestion({ outTxId, inTxId });
    },

    async detectTransfers() {
        if (isDemo()) return { merged: [], suggested: 0 };
        const result = await api.detectTransfers();
        if (result.merged.length) await get().load();
        return result;
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
                ...(body.goalTarget != null
                    ? {
                          goalTarget: body.goalTarget,
                          goalStatus: "active",
                          goalTargetDate: body.goalTargetDate ?? null,
                      }
                    : {}),
            },
        ];
        set({ snapshot: { ...snapshot, categories } });
        return id;
    },

    async patchCategory(id, patch) {
        if (!isDemo()) await api.patchCategory(id, patch);
        const { snapshot } = get();
        const targetGroup = snapshot.groups.find((g) => g.id === patch.groupId);
        const movingToNonGoal = targetGroup != null && targetGroup.kind !== "goal";
        const categories = snapshot.categories.map((c) =>
            c.id === id
                ? {
                      ...c,
                      ...(patch.name != null ? { name: patch.name } : {}),
                      ...(patch.groupId != null ? { groupId: patch.groupId } : {}),
                      ...(patch.keywords != null ? { keywords: patch.keywords } : {}),
                      ...(patch.archived != null ? { archived: patch.archived } : {}),
                      ...(patch.goalTarget != null ? { goalTarget: patch.goalTarget } : {}),
                      ...(patch.goalTargetDate != null
                          ? { goalTargetDate: patch.goalTargetDate }
                          : {}),
                      ...(patch.goalStatus != null ? { goalStatus: patch.goalStatus } : {}),
                      ...(movingToNonGoal &&
                      (c.goalTarget != null || c.goalTargetDate != null || c.goalStatus != null)
                          ? { goalTarget: null, goalTargetDate: null, goalStatus: null }
                          : {}),
                  }
                : c,
        );
        set({ snapshot: { ...snapshot, categories } });
    },

    async archiveGoal(id) {
        if (!isDemo()) await api.archiveGoal(id);
        const { snapshot } = get();
        const categories = snapshot.categories.map((c) =>
            c.id === id ? { ...c, archived: true, goalStatus: "archived" } : c,
        );
        set({ snapshot: { ...snapshot, categories } });
    },

    async deleteCategory(id) {
        if (!isDemo()) await api.deleteCategory(id);
        const { snapshot } = get();
        set({
            snapshot: {
                ...snapshot,
                categories: snapshot.categories.filter((c) => c.id !== id),
                budgets: snapshot.budgets.filter((b) => b.categoryId !== id),
                transactions: snapshot.transactions.map((t) =>
                    t.categoryId === id ? { ...t, categoryId: null } : t,
                ),
            },
        });
    },

    async mergeCategory(id, into) {
        if (!isDemo()) await api.mergeCategory(id, into);
        set({ snapshot: mergeCategories(get().snapshot, id, into) });
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

    async commitImport(rows) {
        if (isDemo()) return { imported: 0, skipped: 0, demo: true };
        const res = await api.importCommit(rows);
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

const initialStoreState = useStore.getState();
const initialSnapshot = structuredClone(initialStoreState.snapshot);
const initialTabs = structuredClone(initialStoreState.tabs);
const initialNextTabId = nextTabId;

export function resetStoreForTests() {
    fillGeneration += 1;
    hiddenEpoch += 1;
    txPatchChain.clear();
    nextTxFieldRevision = 0;
    txFieldRevisions.clear();
    nextTabId = initialNextTabId;
    useStore.setState(
        {
            ...initialStoreState,
            snapshot: structuredClone(initialSnapshot),
            tabs: structuredClone(initialTabs),
        },
        true,
    );
}
