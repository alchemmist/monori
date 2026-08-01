import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { render, type RenderOptions } from "@testing-library/react";
import type { PropsWithChildren, ReactElement } from "react";
import userEvent from "@testing-library/user-event";
import { demoSnapshot } from "../demo/demoData.js";
import { resetStoreForTests, useStore } from "../store.js";
import { theme } from "../ui/theme.js";
import type {
    Account,
    BudgetCell,
    Category,
    CategoryGroup,
    Connection,
    Id,
    Snapshot,
    Transaction,
    Transfer,
} from "../types.js";

/**
 * Component tests render one screen in jsdom against the zustand store, which
 * is the app's only source of data. Two ways to fill it:
 *
 *   - `atDemo()` puts the app on /demo, where the store runs entirely off the
 *     bundled sample dataset and never touches the network — this is what page
 *     tests use, so they exercise the real store code paths;
 *   - `seed({...})` writes a hand-built snapshot straight into the store, for
 *     the empty states and edge shapes the demo data does not contain.
 *
 * Anything that must hit the API is tested by mocking `src/api.js` directly.
 */

function Wrap({ children }: PropsWithChildren) {
    return (
        <MantineProvider theme={theme} forceColorScheme="light" env="test">
            {children}
            <Notifications position="bottom-right" />
        </MantineProvider>
    );
}

/**
 * `env="test"` drops Mantine's mount transitions, and `delay: null` drops
 * user-event's inter-keystroke wait. Both are timers, and timers under a
 * parallel vitest run get starved: without this the dropdown-and-type tests
 * fail a handful at a time depending on machine load.
 */
export function renderUI(ui: ReactElement, options: Omit<RenderOptions, "wrapper"> = {}) {
    return {
        user: userEvent.setup({ delay: null }),
        ...render(ui, { wrapper: Wrap, ...options }),
    };
}

/** Fresh store between tests: zustand keeps state on the module, not the tree. */
export function resetStore() {
    resetStoreForTests();
}

/** Put the app on a path; `isDemo()` reads window.location, not the router. */
export function setPath(path: string) {
    window.history.replaceState({}, "", path);
}

export function atDemo(path = "/demo") {
    setPath(path);
    return demo();
}

/** The demo snapshot, deep-cloned so a mutating test cannot poison the next. */
export function demo() {
    const snapshot = structuredClone(demoSnapshot);
    const withTotal = { ...snapshot, transactionsTotal: snapshot.transactions.length };
    useStore.setState({ snapshot: withTotal, loading: false, error: null, txProgress: null });
    return withTotal;
}

/**
 * A minimal snapshot: one income group with one category, one expense group
 * with two, one account, and whatever the test passes on top.
 */
export interface SnapshotPatch extends Omit<
    Partial<Snapshot>,
    "accounts" | "groups" | "categories" | "budgets" | "transactions" | "transfers" | "connections"
> {
    accounts?: Array<Partial<Account>> | undefined;
    groups?: Array<Partial<CategoryGroup>> | undefined;
    categories?: Array<Partial<Category>> | undefined;
    budgets?: Array<Partial<BudgetCell>> | undefined;
    transactions?: Array<Partial<Transaction>> | undefined;
    transfers?: Array<Partial<Transfer>> | undefined;
    connections?: Array<Partial<Connection>> | undefined;
}

export function buildSnapshot(patch: SnapshotPatch = {}): Snapshot {
    const base: Snapshot = {
        accounts: [
            {
                id: 1,
                name: "Card",
                type: "card",
                icon: "card",
                color: "#5b6472",
                iconImage: null,
                currency: "RUB",
                sort: 1,
                archived: false,
                openingBalance: 100000,
                openingDate: "2026-01-01",
            },
        ],
        groups: [
            { id: 1, name: "Income", kind: "income", sort: 1 },
            { id: 2, name: "Living", kind: "expense", sort: 2 },
        ],
        categories: [
            { id: 1, groupId: 1, name: "Salary", keywords: "", sort: 1, archived: false },
            { id: 2, groupId: 2, name: "Groceries", keywords: "food", sort: 1, archived: false },
            { id: 3, groupId: 2, name: "Rent", keywords: "", sort: 2, archived: false },
        ],
        budgets: [],
        transactions: [],
        transfers: [],
        connections: [],
    };
    const snapshot: Snapshot = {
        ...base,
        ...patch,
        accounts: (patch.accounts ?? base.accounts).map((account, index) => ({
            ...account,
            id: account.id ?? index + 1,
            name: account.name ?? "Account",
            type: account.type ?? "card",
            icon: account.icon ?? "card",
            color: account.color ?? "#5b6472",
            iconImage: account.iconImage ?? null,
            currency: account.currency ?? "RUB",
            sort: account.sort ?? index + 1,
            archived: account.archived ?? false,
            openingBalance: account.openingBalance ?? 0,
            ...(account.openingDate === undefined ? {} : { openingDate: account.openingDate }),
        })),
        groups: (patch.groups ?? base.groups).map((group, index) => ({
            ...group,
            id: group.id ?? index + 1,
            name: group.name ?? "Group",
            kind: group.kind ?? "expense",
            sort: group.sort ?? index + 1,
        })),
        categories: (patch.categories ?? base.categories).map((category, index) => ({
            ...category,
            id: category.id ?? index + 1,
            groupId: category.groupId ?? 2,
            name: category.name ?? "Category",
            keywords: category.keywords ?? "",
            sort: category.sort ?? index + 1,
            archived: category.archived ?? false,
        })),
        budgets: (patch.budgets ?? base.budgets).map((budget) => ({
            ...budget,
            categoryId: budget.categoryId ?? 1,
            year: budget.year ?? 2026,
            month: budget.month ?? 0,
            amount: budget.amount ?? 0,
        })),
        transactions: (patch.transactions ?? base.transactions).map((transaction, index) =>
            tx(transaction.id ?? index + 1, transaction),
        ),
        transfers: (patch.transfers ?? base.transfers).map((transfer, index) => ({
            ...transfer,
            id: transfer.id ?? `transfer-${index + 1}`,
            outTxId: transfer.outTxId ?? 1,
            inTxId: transfer.inTxId ?? 2,
            origin: transfer.origin ?? "manual",
            note: transfer.note ?? "",
        })),
        connections: (patch.connections ?? base.connections ?? []).map((connection, index) => ({
            ...connection,
            id: connection.id ?? index + 1,
            bank: connection.bank ?? "bank",
            kind: connection.kind ?? "browser",
            status: connection.status ?? "connected",
            lastSync: connection.lastSync ?? null,
            lastError: connection.lastError ?? null,
            hasCredentials: connection.hasCredentials ?? true,
            createdAt: connection.createdAt ?? "2026-01-01",
            updatedAt: connection.updatedAt ?? "2026-01-01",
        })),
    };
    return snapshot;
}

export function seed(patch: SnapshotPatch = {}): Snapshot {
    const snapshot = buildSnapshot(patch);
    useStore.setState({
        snapshot: { ...snapshot, transactionsTotal: snapshot.transactions.length },
        loading: false,
        error: null,
        txProgress: null,
    });
    return snapshot;
}

export const tx = (id: Id, patch: Partial<Transaction> = {}): Transaction => ({
    id,
    date: "2026-03-05T00:00:00",
    amount: -1000,
    description: `tx ${id}`,
    bankCategory: "",
    mcc: "",
    categoryId: 2,
    accountId: 1,
    transferId: null,
    comment: "",
    source: "manual",
    ...patch,
});

export * from "@testing-library/react";
