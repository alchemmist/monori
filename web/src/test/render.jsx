import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { demoSnapshot } from "../demo/demoData.js";
import { resetStoreForTests, useStore } from "../store.js";
import { theme } from "../ui/theme.js";

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

function Wrap({ children }) {
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
export function renderUI(ui, options) {
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
export function setPath(path) {
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
export function seed(patch = {}) {
    const snapshot = {
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
        connections: [],
        ...patch,
    };
    useStore.setState({
        snapshot: { ...snapshot, transactionsTotal: snapshot.transactions.length },
        loading: false,
        error: null,
        txProgress: null,
    });
    return snapshot;
}

export const tx = (id, patch = {}) => ({
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

export { userEvent };
export * from "@testing-library/react";
