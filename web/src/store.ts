import { create } from "zustand";
import { api } from "./api.js";
import { demoSnapshot } from "./demo/demoData.js";
import { mergeCategories } from "./mergeCategories.js";
import { compareTx, mergeTransactions } from "./mergeTransactions.js";
import { loadTabs, saveTabs } from "./ui/tabPersist.js";
import type {
    AccountCreate,
    AccountPatch,
    BudgetCell,
    CategoryCreate,
    CategoryPatch,
    Id,
    ImportResult,
    ImportRow,
    Snapshot,
    SyncResult,
    TabDescriptor,
    ToastMessage,
    Transaction,
    TransactionCreate,
    TransactionPatch,
    TransactionSplit,
    TransferCreate,
    TransferSuggestion,
    User,
} from "./types.js";

const TRANSACTION_PATCH_KEYS = [
    "date",
    "amount",
    "accountId",
    "description",
    "bankCategory",
    "mcc",
    "categoryId",
    "comment",
    "hidden",
] satisfies ReadonlyArray<keyof TransactionPatch>;

interface StoreState {
    snapshot: Snapshot | null;
    loading: boolean;
    txProgress: { loaded: number; total: number } | null;
    error: string | null;
    toast: ToastMessage | null;
    user: User | null;
    authChecked: boolean;
    tabs: TabDescriptor[];
    hiddenTx: Transaction[] | null;
    adminTick: number;
    setTabs: (tabs: TabDescriptor[]) => void;
    openTab: (kind: string, props?: Record<string, unknown>, key?: string | null) => void;
    closeTab: (id: number) => void;
    closeTabByKey: (key: string) => void;
    bumpAdminTick: () => void;
    checkAuth: () => Promise<void>;
    login: (email: string, password: string) => Promise<void>;
    register: (email: string, password: string) => Promise<void>;
    patchMe: (patch: Partial<Pick<User, "defaultAccountId">>) => Promise<User>;
    logout: () => void;
    load: () => Promise<void>;
    fillTransactions: (generation?: object) => Promise<void>;
    notify: (toast: ToastMessage) => void;
    setBudget: (categoryId: Id, year: number, month: number, amount: number) => Promise<void>;
    fillBudgetForward: (categoryId: Id, year: number, month: number) => Promise<number>;
    setBudgets: (cells: BudgetCell[]) => Promise<void>;
    copyBudgetYear: (fromYear: number, toYear: number) => Promise<number>;
    setTxCategory: (txId: Id, categoryId: Id | null) => void;
    addTransaction: (body: TransactionCreate) => Promise<Transaction>;
    updateTransaction: (txId: Id, patch: TransactionPatch) => Promise<void>;
    replaceTransactionSplits: (
        txId: Id,
        parts: Array<Omit<TransactionSplit, "id">>,
    ) => Promise<TransactionSplit[] | undefined>;
    deleteTransaction: (txId: Id) => Promise<boolean>;
    loadHiddenTx: () => Promise<void>;
    hideTx: (txId: Id) => void;
    unhideTx: (txId: Id) => void;
    setTxAccount: (txId: Id, accountId: Id) => void;
    createAccount: (body: AccountCreate) => Promise<Id>;
    patchAccount: (id: Id, patch: AccountPatch) => Promise<void>;
    deleteAccount: (id: Id, reassignTo?: Id | null) => Promise<void>;
    reconcileAccount: (id: Id, actualBalance: number) => Promise<{ delta: number }>;
    createTransfer: (body: TransferCreate) => Promise<string>;
    linkTransfer: (outTxId: Id, inTxId: Id) => Promise<string>;
    splitTransfer: (transferId: string) => Promise<void>;
    deleteTransferWithLegs: (transferId: string) => Promise<void>;
    transferSuggestions: () => Promise<{ rows: TransferSuggestion[]; transactions: Transaction[] }>;
    dismissTransferSuggestion: (outTxId: Id, inTxId: Id) => Promise<void>;
    detectTransfers: () => Promise<{ merged: string[]; suggested: number }>;
    createCategory: (body: CategoryCreate) => Promise<Id>;
    patchCategory: (id: Id, patch: CategoryPatch) => Promise<void>;
    archiveGoal: (id: Id) => Promise<void>;
    deleteCategory: (id: Id) => Promise<void>;
    mergeCategory: (id: Id, into: Id) => Promise<void>;
    moveCategory: (
        id: Id,
        toGroupId: Id,
        orderedIds: Id[],
        categoryPatch?: CategoryPatch,
    ) => Promise<void>;
    createGroup: (body: { name: string; kind: string }) => Promise<Id>;
    patchGroup: (id: Id, patch: { name?: string; kind?: string }) => Promise<void>;
    deleteGroup: (id: Id) => Promise<void>;
    reorderGroups: (orderedIds: Id[]) => Promise<void>;
    commitImport: (rows: ImportRow[]) => Promise<ImportResult>;
    createConnection: (body: {
        bank: string;
        kind: string;
        credentials: Record<string, string>;
    }) => Promise<{ id: Id }>;
    deleteConnection: (id: Id) => Promise<void>;
    syncConnection: (id: Id) => Promise<SyncResult>;
    submitConnectionSms: (id: Id, code: string) => Promise<SyncResult>;
    cancelConnectionSync: (id: Id) => Promise<void>;
}

/** Rows per background chunk once the light snapshot has painted. */
export const TX_CHUNK = 1000;

/** How long chunks are allowed to pile up before they land in the snapshot.
 * Every snapshot write re-runs the budget/dashboard math over the whole ledger,
 * so on a fast link the chunks are coalesced instead of recomputing per chunk. */
export const TX_FLUSH_MS = 250;

/** Replaced by every load(); a fill whose generation is stale drops its results. */
let fillGeneration = {};

let snapshotReplacementEpoch = {};

/** Replaced by every hide/unhide, so an in-flight hidden-list fetch can tell it
 * is stale and must not overwrite the newer optimistic state. */
let hiddenEpoch = {};
let hiddenRevisions = new Map<Id, object>();

/** Rapid hide→unhide on one row must reach the server in order, or the earlier
 * PATCH could land last and win — so per-transaction PATCHes are chained. */
const txPatchChain = new Map<Id, Promise<unknown>>();
function chainedPatchTx(id: Id, patch: TransactionPatch) {
    const prev = txPatchChain.get(id) ?? Promise.resolve();
    const next = prev.catch(() => {}).then(() => api.patchTx(id, patch));
    txPatchChain.set(id, next);
    next.catch(() => {}).finally(() => {
        if (txPatchChain.get(id) === next) txPatchChain.delete(id);
    });
    return next;
}

let budgetOperationTail: Promise<void> = Promise.resolve();
let nextBudgetRevision = 0;
const budgetRevisions = new Map<string, number>();
const failedBudgetWrites = new Map<string, unknown>();
let budgetBaselines = new Map<string, BudgetCell | undefined>();
let sessionEpoch = {};
let budgetSessionToken: string | null = null;

class SessionChangedError extends Error {}

function resetBudgetSession() {
    sessionEpoch = {};
    budgetSessionToken = null;
    nextBudgetRevision = 0;
    budgetRevisions.clear();
    failedBudgetWrites.clear();
    budgetBaselines = new Map();
    hiddenRevisions = new Map();
}

function sessionStamp() {
    const token = localStorage.getItem("monori_token");
    if (token !== budgetSessionToken) {
        resetBudgetSession();
        budgetSessionToken = token;
    }
    return { epoch: sessionEpoch, token };
}

function assertCurrentSession(stamp: ReturnType<typeof sessionStamp>) {
    if (stamp.epoch !== sessionEpoch || stamp.token !== localStorage.getItem("monori_token")) {
        throw new SessionChangedError("session changed before budget operation completed");
    }
}

function chainedBudgetOperation<T>(
    stamp: ReturnType<typeof sessionStamp>,
    operation: () => Promise<T>,
): Promise<T> {
    const result = budgetOperationTail.then(async () => {
        assertCurrentSession(stamp);
        const value = await operation();
        assertCurrentSession(stamp);
        return value;
    });
    budgetOperationTail = result.then(
        () => undefined,
        () => undefined,
    );
    return result;
}

function budgetKey(categoryId: Id, year: number, month: number) {
    return `${categoryId}-${year}-${month}`;
}

// Each optimistic transaction edit owns revisions for the fields it changes.
// A failed older request must never undo a newer edit to the same field.
let nextTxFieldRevision = 0;
let txFieldRevisions = new Map<Id, Map<keyof TransactionPatch, number>>();

let nextSplitRevision = 0;
const splitRevisions = new Map<Id, number>();

const now = () => (typeof performance !== "undefined" ? performance.now() : 0);

function requireSnapshot(snapshot: Snapshot | null): Snapshot {
    if (!snapshot) throw new Error("store snapshot is not loaded");
    return snapshot;
}

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

export const useStore = create<StoreState>((set, get) => ({
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
        if (token == null || token === "") {
            // no session — drop any restored tabs so they cannot resurface for
            // whoever signs in on this browser next
            get().setTabs([]);
            resetBudgetSession();
            set({ authChecked: true });
            return;
        }
        try {
            const user = await api.authMe(token);
            resetBudgetSession();
            set({ user, authChecked: true });
        } catch {
            resetBudgetSession();
            localStorage.removeItem("monori_token");
            get().setTabs([]);
            set({ user: null, authChecked: true });
        }
    },

    async login(email, password) {
        const { access_token } = await api.authLogin(email, password);
        resetBudgetSession();
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
        resetBudgetSession();
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
        const generation = (fillGeneration = {});
        // Do not briefly render a prior account's hidden ledger while the new
        // snapshot is loading. The epoch also discards any old hidden request.
        const reloadHidden = get().hiddenTx !== null;
        hiddenEpoch = {};
        set({ hiddenTx: null });
        if (isDemo()) {
            const snapshot = structuredClone(demoSnapshot);
            snapshotReplacementEpoch = {};
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
            snapshotReplacementEpoch = {};
            set({ snapshot, loading: false, error: null });
        } catch (e) {
            set({ error: String(e), loading: false, txProgress: null });
            return;
        }
        if (reloadHidden) void get().loadHiddenTx();
        void get().fillTransactions(generation);
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
        let pending: Transaction[] = [];
        let flushedAt = now();
        const flush = (done: boolean) => {
            const current = requireSnapshot(get().snapshot);
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
                const loaded = requireSnapshot(get().snapshot).transactions.length + pending.length;
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
        const stamp = sessionStamp();
        const key = budgetKey(categoryId, year, month);
        const revision = ++nextBudgetRevision;
        budgetRevisions.set(key, revision);
        const snapshot = requireSnapshot(get().snapshot);
        const before = snapshot.budgets.find(
            (b) => b.categoryId === categoryId && b.year === year && b.month === month,
        );
        if (!budgetBaselines.has(key)) budgetBaselines.set(key, before);
        const budgets = snapshot.budgets.filter(
            (b) => !(b.categoryId === categoryId && b.year === year && b.month === month),
        );
        if (amount !== 0) budgets.push({ categoryId, year, month, amount });
        set({ snapshot: { ...snapshot, budgets } });
        if (isDemo()) return Promise.resolve();
        const write = chainedBudgetOperation(stamp, async () => {
            try {
                await api.putBudget({ categoryId, year, month, amount });
                assertCurrentSession(stamp);
                failedBudgetWrites.delete(key);
                budgetBaselines.set(
                    key,
                    amount === 0 ? undefined : { categoryId, year, month, amount },
                );
            } catch (error) {
                if (stamp.token === localStorage.getItem("monori_token")) {
                    failedBudgetWrites.set(key, error);
                    if (budgetRevisions.get(key) === revision) {
                        const current = requireSnapshot(get().snapshot);
                        const restored = current.budgets.filter(
                            (b) =>
                                !(
                                    b.categoryId === categoryId &&
                                    b.year === year &&
                                    b.month === month
                                ),
                        );
                        const baseline = budgetBaselines.get(key);
                        if (baseline) restored.push(baseline);
                        set({ snapshot: { ...current, budgets: restored } });
                    }
                }
                throw error;
            }
        });
        write.catch((e) => {
            if (
                !(e instanceof SessionChangedError) &&
                stamp.epoch === sessionEpoch &&
                stamp.token === localStorage.getItem("monori_token")
            ) {
                set({
                    toast: { title: "Failed to save budget", theme: "danger", content: String(e) },
                });
            }
        });
        void write
            .finally(() => {
                if (stamp.epoch === sessionEpoch && budgetRevisions.get(key) === revision) {
                    budgetBaselines.delete(key);
                }
            })
            .catch(() => undefined);
        return write;
    },

    /** Copy one category's current month into every later month of the year.
     * Unlike a display-only fill, this is one bulk request, so the resulting
     * plan is persisted atomically before the grid updates. */
    async fillBudgetForward(categoryId, year, month) {
        const snapshot = requireSnapshot(get().snapshot);
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
        const snapshot = requireSnapshot(get().snapshot);
        const keys = new Set(cells.map((c) => `${c.categoryId}-${c.year}-${c.month}`));
        const budgets = snapshot.budgets.filter(
            (b) => !keys.has(`${b.categoryId}-${b.year}-${b.month}`),
        );
        budgets.push(...cells.filter((c) => c.amount !== 0));
        set({ snapshot: { ...snapshot, budgets } });
    },

    copyBudgetYear(fromYear, toYear) {
        const stamp = sessionStamp();
        const revision = nextBudgetRevision;
        return chainedBudgetOperation(stamp, async () => {
            const failedWrite = failedBudgetWrites.values().next();
            if (failedWrite.done === false) throw failedWrite.value;

            let copied: number;
            let targetBudgets: BudgetCell[];
            if (isDemo()) {
                targetBudgets = requireSnapshot(get().snapshot)
                    .budgets.filter((b) => b.year === fromYear)
                    .map((b) => ({ ...b, year: toYear }));
                copied = targetBudgets.length;
            } else {
                const response = await api.copyBudgetYear(fromYear, toYear);
                copied = response.copied;
                targetBudgets = response.budgets;
            }

            const changedAfterRequest = (b: BudgetCell) =>
                (budgetRevisions.get(budgetKey(b.categoryId, b.year, b.month)) ?? 0) > revision;
            const snapshot = requireSnapshot(get().snapshot);
            const budgets = snapshot.budgets.filter(
                (b) => b.year !== toYear || changedAfterRequest(b),
            );
            budgets.push(...targetBudgets.filter((b) => !changedAfterRequest(b)));
            set({ snapshot: { ...snapshot, budgets } });
            return copied;
        });
    },

    setTxCategory(txId, categoryId) {
        void get().updateTransaction(txId, { categoryId: categoryId ?? null });
    },

    /** Record a transaction by hand. The row is merged straight into the loaded
     * ledger instead of reloading the whole snapshot, so entering a run of them
     * one after another never blanks the page or loses the scroll position —
     * every derived view (budget, analytics, balances) recomputes from the
     * snapshot anyway. Returns the created row. */
    async addTransaction(body) {
        const snapshot = requireSnapshot(get().snapshot);
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
        const current = requireSnapshot(get().snapshot);
        set({
            snapshot: {
                ...current,
                transactions: mergeTransactions(current.transactions, [tx]),
                transactionsTotal: (current.transactionsTotal ?? current.transactions.length) + 1,
            },
        });
        // Creating a row shifts every older-page offset. Restart the fill so
        // its captured total and offsets cannot overwrite or skip this insert.
        if (get().txProgress) void get().fillTransactions((fillGeneration = {}));
        return tx;
    },

    /** Edit a transaction's own fields — date, description, amount, comment.
     * Optimistic like every other ledger edit, but a failed save rolls the row
     * back: unlike a category, a wrong amount would keep every balance and
     * budget on the page lying until the next reload. A changed date moves the
     * row, so the ledger is re-sorted into canonical order. */
    async updateTransaction(txId, patch) {
        const stamp = sessionStamp();
        const replacementEpoch = snapshotReplacementEpoch;
        const snapshot = requireSnapshot(get().snapshot);
        const before = snapshot.transactions.find((t) => t.id === txId);
        if (!before) return;
        const revision = (nextTxFieldRevision += 1);
        const revisions = txFieldRevisions.get(txId) ?? new Map<keyof TransactionPatch, number>();
        const patchKeys = TRANSACTION_PATCH_KEYS.filter((key) => patch[key] !== undefined);
        patchKeys.forEach((key) => revisions.set(key, revision));
        txFieldRevisions.set(txId, revisions);
        const rows = snapshot.transactions.map((t) => (t.id === txId ? { ...t, ...patch } : t));
        rows.sort(compareTx);
        set({ snapshot: { ...snapshot, transactions: rows } });
        if (isDemo()) return;
        try {
            await api.patchTx(
                txId,
                patch.categoryId === null ? { ...patch, categoryId: 0 } : patch,
            );
        } catch (e) {
            if (stamp.epoch !== sessionEpoch || replacementEpoch !== snapshotReplacementEpoch)
                return;
            const cur = requireSnapshot(get().snapshot);
            const undo = Object.fromEntries(
                patchKeys
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
            patchKeys.forEach((key) => {
                if (revisions.get(key) === revision) revisions.delete(key);
            });
            if (!revisions.size) txFieldRevisions.delete(txId);
        }
    },

    async replaceTransactionSplits(txId, parts) {
        const snapshot = requireSnapshot(get().snapshot);
        const before = snapshot.transactions.find((transaction) => transaction.id === txId);
        if (!before) return;
        const optimistic = parts.map((part, index) => ({ id: `new-${index}`, ...part }));
        const update = (splits: TransactionSplit[]) =>
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
            const current = requireSnapshot(get().snapshot);
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
                const current = requireSnapshot(get().snapshot);
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
        const snapshot = requireSnapshot(get().snapshot);
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
            const cur = requireSnapshot(get().snapshot);
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
        const stamp = sessionStamp();
        const replacementEpoch = snapshotReplacementEpoch;
        const { hiddenTx } = get();
        const snapshot = requireSnapshot(get().snapshot);
        const t = snapshot.transactions.find((x) => x.id === txId);
        if (!t) return;
        const revision = {};
        hiddenRevisions.set(txId, revision);
        set({
            snapshot: {
                ...snapshot,
                transactions: snapshot.transactions.filter((x) => x.id !== txId),
                transactionsTotal: Math.max(0, (snapshot.transactionsTotal ?? 1) - 1),
            },
            hiddenTx: [...(hiddenTx ?? []), { ...t, hidden: true }].sort(compareTx),
        });
        if (isDemo()) return;
        hiddenEpoch = {};
        void (async () => {
            try {
                await chainedPatchTx(txId, { hidden: true });
                if (get().txProgress) void get().fillTransactions((fillGeneration = {}));
            } catch (e) {
                if (
                    hiddenRevisions.get(txId) === revision &&
                    stamp.token === localStorage.getItem("monori_token") &&
                    replacementEpoch === snapshotReplacementEpoch
                ) {
                    const current = requireSnapshot(get().snapshot);
                    set({
                        snapshot: {
                            ...current,
                            transactions: mergeTransactions(current.transactions, [t]),
                            transactionsTotal: (current.transactionsTotal ?? 0) + 1,
                        },
                        hiddenTx: (get().hiddenTx ?? []).filter((row) => row.id !== txId),
                        toast: {
                            title: "Failed to hide transaction",
                            theme: "danger",
                            content: String(e),
                        },
                    });
                }
            }
        })();
    },

    unhideTx(txId) {
        const stamp = sessionStamp();
        const replacementEpoch = snapshotReplacementEpoch;
        const { hiddenTx } = get();
        const snapshot = requireSnapshot(get().snapshot);
        const t = (hiddenTx ?? []).find((x) => x.id === txId);
        if (!t || !hiddenTx) return;
        const revision = {};
        hiddenRevisions.set(txId, revision);
        set({
            snapshot: {
                ...snapshot,
                transactions: mergeTransactions(snapshot.transactions, [{ ...t, hidden: false }]),
                transactionsTotal: (snapshot.transactionsTotal ?? 0) + 1,
            },
            hiddenTx: hiddenTx.filter((x) => x.id !== txId),
        });
        if (isDemo()) return;
        hiddenEpoch = {};
        void (async () => {
            try {
                await chainedPatchTx(txId, { hidden: false });
                if (get().txProgress) void get().fillTransactions((fillGeneration = {}));
            } catch (e) {
                if (
                    hiddenRevisions.get(txId) === revision &&
                    stamp.token === localStorage.getItem("monori_token") &&
                    replacementEpoch === snapshotReplacementEpoch
                ) {
                    const current = requireSnapshot(get().snapshot);
                    set({
                        snapshot: {
                            ...current,
                            transactions: current.transactions.filter((row) => row.id !== txId),
                            transactionsTotal: Math.max(0, (current.transactionsTotal ?? 1) - 1),
                        },
                        hiddenTx: [...(get().hiddenTx ?? []), t].sort(compareTx),
                        toast: {
                            title: "Failed to unhide transaction",
                            theme: "danger",
                            content: String(e),
                        },
                    });
                }
            }
        })();
    },

    setTxAccount(txId, accountId) {
        void get().updateTransaction(txId, { accountId });
    },

    async createAccount(body) {
        const snapshot = requireSnapshot(get().snapshot);
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
                iconImage: body.iconImage == null || body.iconImage === "" ? null : body.iconImage,
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
        const snapshot = requireSnapshot(get().snapshot);
        const accounts = snapshot.accounts.map((a) => (a.id === id ? { ...a, ...patch } : a));
        set({ snapshot: { ...snapshot, accounts } });
    },

    async deleteAccount(id, reassignTo) {
        if (!isDemo()) await api.deleteAccount(id, reassignTo);
        const snapshot = requireSnapshot(get().snapshot);
        set({
            snapshot: {
                ...snapshot,
                accounts: snapshot.accounts.filter((a) => a.id !== id),
                transactions:
                    reassignTo != null
                        ? snapshot.transactions.map((t) =>
                              t.accountId === id ? { ...t, accountId: reassignTo } : t,
                          )
                        : snapshot.transactions,
            },
        });
    },

    async reconcileAccount(id, actualBalance) {
        if (isDemo()) {
            const snapshot = requireSnapshot(get().snapshot);
            const account = snapshot.accounts.find((candidate) => candidate.id === id);
            const balance = account
                ? snapshot.transactions
                      .filter((t) => t.accountId === id)
                      .reduce(
                          (sum, transaction) => sum + transaction.amount,
                          account.openingBalance ?? 0,
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
            const snapshot = requireSnapshot(get().snapshot);
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
                outTxId: rows[0]!.id,
                inTxId: rows[1]!.id,
                origin: "manual",
                note: body.comment ?? "",
                createdAt: body.date,
            };
            set({
                snapshot: {
                    ...snapshot,
                    transactions: [...snapshot.transactions, ...rows],
                    transfers: [...snapshot.transfers, entity],
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
            const snapshot = requireSnapshot(get().snapshot);
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
                        ...snapshot.transfers,
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
        const snapshot = requireSnapshot(get().snapshot);
        set({
            snapshot: {
                ...snapshot,
                transactions: snapshot.transactions.map((t) =>
                    t.transferId === transferId ? { ...t, transferId: null } : t,
                ),
                transfers: snapshot.transfers.filter((x) => x.id !== transferId),
            },
        });
    },

    /** Split, then delete both rows — the one path that really removes the
     * money. Kept separate from splitTransfer so nothing can destroy a bank's
     * own transactions by accident. */
    async deleteTransferWithLegs(transferId) {
        const transactions = requireSnapshot(get().snapshot).transactions;
        const deleted = isDemo()
            ? transactions.filter((transaction) => transaction.transferId === transferId).length
            : (await api.deleteTransferWithLegs(transferId)).deleted;
        const snapshot = requireSnapshot(get().snapshot);
        set({
            snapshot: {
                ...snapshot,
                transactions: snapshot.transactions.filter((t) => t.transferId !== transferId),
                transfers: snapshot.transfers.filter((x) => x.id !== transferId),
                transactionsTotal: Math.max(
                    0,
                    (snapshot.transactionsTotal ?? snapshot.transactions.length) - deleted,
                ),
            },
        });
        if (get().txProgress) void get().fillTransactions((fillGeneration = {}));
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
        const snapshot = requireSnapshot(get().snapshot);
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
        const snapshot = requireSnapshot(get().snapshot);
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
        const snapshot = requireSnapshot(get().snapshot);
        const categories = snapshot.categories.map((c) =>
            c.id === id ? { ...c, archived: true, goalStatus: "archived" } : c,
        );
        set({ snapshot: { ...snapshot, categories } });
    },

    async deleteCategory(id) {
        if (!isDemo()) await api.deleteCategory(id);
        const snapshot = requireSnapshot(get().snapshot);
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
        set({ snapshot: mergeCategories(requireSnapshot(get().snapshot), id, into) });
    },

    /** Kanban drop: move a card to `toGroupId` and lay out every category by the
     *  global order in `orderedIds` (assigns 1..N to sort). Optimistic; the group
     *  change and the reorder are both persisted, then resynced on failure. */
    async moveCategory(id, toGroupId, orderedIds, categoryPatch = {}) {
        const snapshot = requireSnapshot(get().snapshot);
        const cat = snapshot.categories.find((c) => c.id === id);
        const groupChanged = cat != null && cat.groupId !== toGroupId;
        const sortById = new Map(orderedIds.map((cid, i) => [cid, i + 1]));
        const categories = snapshot.categories.map((c) => ({
            ...c,
            groupId: c.id === id ? toGroupId : c.groupId,
            ...(c.id === id ? categoryPatch : {}),
            sort: sortById.get(c.id) ?? c.sort,
        }));
        set({ snapshot: { ...snapshot, categories } });
        if (isDemo()) return;
        try {
            const patchBody = cat
                ? { ...(groupChanged ? { groupId: toGroupId } : {}), ...categoryPatch }
                : {};
            if (Object.keys(patchBody).length > 0) await api.patchCategory(id, patchBody);
            await api.reorderCategories(orderedIds);
        } catch (e) {
            get().notify({ title: "Failed to move category", theme: "danger", content: String(e) });
            await get().load();
            throw e;
        }
    },

    async createGroup(body) {
        const snapshot = requireSnapshot(get().snapshot);
        const id = isDemo()
            ? Math.max(0, ...snapshot.groups.map((g) => g.id)) + 1
            : (await api.createGroup(body)).id;
        const groups = [...snapshot.groups, { id, name: body.name, kind: body.kind, sort: 1e9 }];
        set({ snapshot: { ...snapshot, groups } });
        return id;
    },

    async patchGroup(id, patch) {
        if (!isDemo()) await api.patchGroup(id, patch);
        const snapshot = requireSnapshot(get().snapshot);
        const groups = snapshot.groups.map((g) => (g.id === id ? { ...g, ...patch } : g));
        set({ snapshot: { ...snapshot, groups } });
    },

    async deleteGroup(id) {
        if (!isDemo()) await api.deleteGroup(id);
        const snapshot = requireSnapshot(get().snapshot);
        set({ snapshot: { ...snapshot, groups: snapshot.groups.filter((g) => g.id !== id) } });
    },

    async reorderGroups(orderedIds) {
        const snapshot = requireSnapshot(get().snapshot);
        const sortById = new Map(orderedIds.map((gid, i) => [gid, i + 1]));
        const groups = snapshot.groups.map((g) => {
            const sort = sortById.get(g.id) ?? g.sort;
            return { ...g, ...(sort === undefined ? {} : { sort }) };
        });
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
    fillGeneration = {};
    snapshotReplacementEpoch = {};
    hiddenEpoch = {};
    txPatchChain.clear();
    nextTxFieldRevision = 0;
    txFieldRevisions = new Map();
    budgetOperationTail = Promise.resolve();
    sessionEpoch = {};
    nextBudgetRevision = 0;
    budgetRevisions.clear();
    failedBudgetWrites.clear();
    budgetBaselines = new Map();
    hiddenRevisions = new Map();
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
