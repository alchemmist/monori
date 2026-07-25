import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderUI, resetStore, screen, seed, tx, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import TransactionsPage from "./TransactionsPage.jsx";

vi.mock("../api.js");
vi.mock("../components/ImportDialog.jsx", () => ({ default: ({ onClose }) => <button onClick={onClose}>Close import</button> }));
vi.mock("../components/TransferDialog.jsx", () => ({ default: ({ accounts, onClose }) => <button onClick={onClose}>Transfer with {accounts.length} accounts</button> }));

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
                tx(1, { description: "Paycheck", amount: 1000, source: "adjustment", date: "2026-03-01" }),
                tx(2, { description: "Transfer out", transferId: 11, accountId: 2, date: "2026-03-02" }),
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

    it("filters by free-text and clears the search", async () => {
        seed({ transactions: [tx(1, { description: "Coffee shop", bankCategory: "Cafe" }), tx(2, { description: "Monthly rent", bankCategory: "Housing" })] });
        const { user } = renderUI(<TransactionsPage />);
        const search = screen.getByLabelText("Search description");
        await user.type(search, "housing");
        expect(screen.getByText("Monthly rent")).toBeInTheDocument();
        expect(screen.queryByText("Coffee shop")).not.toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Clear search" }));
        expect(screen.getByText("Coffee shop")).toBeInTheDocument();
    });

    it("shows the empty state when filters find no rows", async () => {
        seed({ transactions: [tx(1, { description: "Coffee" })] });
        const { user } = renderUI(<TransactionsPage />);
        await user.type(screen.getByLabelText("Search description"), "missing");
        expect(screen.getByText("Nothing found")).toBeInTheDocument();
    });

    it("changes an ordinary row's account and category", async () => {
        seed({ accounts, groups, categories, transactions: [tx(1, { categoryId: 2, accountId: 1 })] });
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

    it("opens import and transfer controls and disables transfer with one active account", async () => {
        seed({ accounts, transactions: [] });
        const { user, unmount } = renderUI(<TransactionsPage />);
        await user.click(screen.getByRole("button", { name: "Import statement" }));
        expect(screen.getByRole("button", { name: "Close import" })).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Transfer" }));
        expect(screen.getByRole("button", { name: "Transfer with 3 accounts" })).toBeInTheDocument();
        unmount();
        seed({ accounts: [accounts[0]], transactions: [] });
        renderUI(<TransactionsPage />);
        expect(screen.getByRole("button", { name: "Transfer" })).toBeDisabled();
    });
});
