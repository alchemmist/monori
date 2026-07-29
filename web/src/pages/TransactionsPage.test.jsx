import { beforeEach, describe, expect, it, vi } from "vitest";
import {
    fireEvent,
    renderUI,
    resetStore,
    screen,
    seed,
    tx,
    waitFor,
    within,
} from "../test/render.jsx";
import { useStore } from "../store.js";
import TransactionsPage from "./TransactionsPage.jsx";

vi.mock("../api.js");
vi.mock("../components/ImportDialog.jsx", () => ({
    default: ({ onClose }) => <button onClick={onClose}>Close import</button>,
}));
vi.mock("../components/TransferDialog.jsx", () => ({
    default: ({ accounts, onClose }) => (
        <button onClick={onClose}>Transfer with {accounts.length} accounts</button>
    ),
}));

const accounts = [
    { id: 1, name: "Card", archived: false },
    { id: 2, name: "Savings", archived: false },
    { id: 3, name: "Old card", archived: true },
];
const groups = [{ id: 2, name: "Living", kind: "expense", sort: 1 }];
const categories = [
    { id: 2, groupId: 2, name: "Food", archived: false, sort: 1 },
    { id: 3, groupId: 2, name: "Archived", archived: true, sort: 2 },
];

describe("TransactionsPage", () => {
    beforeEach(() => {
        resetStore();
        vi.clearAllMocks();
    });

    it("renders transactions, source tags, totals and progressive loading", () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                tx(1, {
                    description: "Paycheck",
                    amount: 1000,
                    source: "adjustment",
                    date: "2026-03-01",
                }),
                tx(2, {
                    description: "Transfer out",
                    transferId: 11,
                    accountId: 2,
                    date: "2026-03-02",
                }),
            ],
        });
        useStore.setState({ txProgress: { loaded: 2, total: 5 } });
        renderUI(<TransactionsPage />);
        expect(screen.getByText("2 transactions")).toBeInTheDocument();
        expect(screen.getByText("Paycheck")).toBeInTheDocument();
        expect(screen.getByText("adjustment")).toBeInTheDocument();
        expect(screen.getByText("transfer")).toBeInTheDocument();
        expect(screen.getByLabelText("Loading older transactions: 2 of 5")).toBeInTheDocument();
        expect(screen.getAllByText("Savings").length).toBeGreaterThan(0);
    });

    it("shows a neutral category for expanded transfer legs", async () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                tx(1, {
                    description: "Transfer out",
                    amount: -1000,
                    transferId: 11,
                    accountId: 1,
                }),
                tx(2, {
                    description: "Transfer in",
                    amount: 1000,
                    transferId: 11,
                    accountId: 2,
                }),
            ],
        });
        const { user } = renderUI(<TransactionsPage />);
        await user.click(screen.getByRole("button", { name: "Show both transactions" }));

        for (const description of ["Transfer out", "Transfer in"]) {
            const row = screen.getByText(description).closest("tr");
            expect(within(row).getByText("—")).toBeInTheDocument();
            expect(within(row).queryByText("Split")).not.toBeInTheDocument();
        }
    });

    it("filters by free-text and clears the search", async () => {
        seed({
            transactions: [
                tx(1, { description: "Coffee shop", bankCategory: "Cafe" }),
                tx(2, { description: "Monthly rent", bankCategory: "Housing" }),
            ],
        });
        const { user } = renderUI(<TransactionsPage />);
        const search = screen.getByLabelText("Search description or comment");
        await user.type(search, "housing");
        expect(screen.getByText("Monthly rent")).toBeInTheDocument();
        expect(screen.queryByText("Coffee shop")).not.toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Clear search" }));
        expect(screen.getByText("Coffee shop")).toBeInTheDocument();
    });

    it("shows the empty state when filters find no rows", async () => {
        seed({ transactions: [tx(1, { description: "Coffee" })] });
        const { user } = renderUI(<TransactionsPage />);
        await user.type(screen.getByLabelText("Search description or comment"), "missing");
        expect(screen.getByText("Nothing found")).toBeInTheDocument();
    });

    it("filters by year, account, category and uncategorized state", async () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                tx(1, { description: "Old food", date: "2025-12-01", accountId: 1, categoryId: 2 }),
                tx(2, {
                    description: "New uncategorized",
                    date: "2026-03-01",
                    accountId: 2,
                    categoryId: null,
                }),
                tx(3, { description: "New food", date: "2026-03-02", accountId: 1, categoryId: 2 }),
            ],
        });
        const { container, user } = renderUI(<TransactionsPage />);
        const toolbar = within(container.querySelector(".budget-toolbar"));
        /** Toolbar filters carry their current selection as their label. */
        const pick = async (current, option) => {
            await user.click(toolbar.getByRole("button", { name: current }));
            await user.click(screen.getByRole("option", { name: option, hidden: true }));
        };

        await pick("All years", "2025");
        expect(screen.getByText("Old food")).toBeInTheDocument();
        expect(screen.queryByText("New food")).not.toBeInTheDocument();

        await pick("2025", "All years");
        await pick("All accounts", "Savings");
        expect(screen.getByText("New uncategorized")).toBeInTheDocument();
        expect(screen.queryByText("New food")).not.toBeInTheDocument();

        await pick("All categories", "Uncategorized");
        expect(screen.getByText("New uncategorized")).toBeInTheDocument();
        await pick("Savings", "All accounts");
        expect(screen.getByText("New uncategorized")).toBeInTheDocument();
        expect(screen.queryByText("Old food")).not.toBeInTheDocument();
    });

    it("keeps archived account and category selected on legacy rows", async () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [tx(1, { accountId: 3, categoryId: 3 })],
        });
        renderUI(<TransactionsPage />);
        const row = screen.getByText("tx 1").closest("tr");
        expect(row).toHaveTextContent("Old card");
        expect(row).toHaveTextContent("Archived");
        expect(row.querySelectorAll("button.gsel")).toHaveLength(2);
    });

    it("changes an ordinary row's account and category", async () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [tx(1, { categoryId: 2, accountId: 1 })],
        });
        const setTxAccount = vi.spyOn(useStore.getState(), "setTxAccount").mockResolvedValue();
        const setTxCategory = vi.spyOn(useStore.getState(), "setTxCategory").mockResolvedValue();
        const { user } = renderUI(<TransactionsPage />);
        const row = screen.getByText("tx 1").closest("tr");
        const selects = row.querySelectorAll("button.gsel");
        await user.click(selects[0]);
        fireEvent.click(screen.getByRole("option", { name: "Savings", hidden: true }));
        await waitFor(() => expect(setTxAccount).toHaveBeenCalledWith(1, 2));
        await user.click(selects[1]);
        fireEvent.click(screen.getByRole("option", { name: "Food", hidden: true }));
        await waitFor(() => expect(setTxCategory).toHaveBeenCalledWith(1, 2));
    });

    it("offers expense categories for a positive refund", async () => {
        seed({
            accounts,
            groups: [...groups, { id: 4, name: "Income", kind: "income", sort: 2 }],
            categories: [
                ...categories,
                { id: 4, groupId: 4, name: "Salary", archived: false, sort: 1 },
            ],
            transactions: [tx(1, { amount: 2400, categoryId: null, accountId: 1 })],
        });
        const { user } = renderUI(<TransactionsPage />);
        const row = screen.getByText("tx 1").closest("tr");

        await user.click(row.querySelectorAll("button.gsel")[1]);

        expect(screen.getByRole("option", { name: "Food", hidden: true })).toBeInTheDocument();
        expect(screen.getByRole("option", { name: "Salary", hidden: true })).toBeInTheDocument();
    });

    it("offers import and transfer controls and disables transfer with one active account", () => {
        seed({ accounts, transactions: [] });
        const { unmount } = renderUI(<TransactionsPage />);
        expect(screen.getByRole("button", { name: "Import statement" })).toBeEnabled();
        expect(screen.getByRole("button", { name: "Transfer" })).toBeEnabled();
        unmount();
        seed({ accounts: [accounts[0]], transactions: [] });
        renderUI(<TransactionsPage />);
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
    });
});
