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
            transactions: [
                tx(1, { amount: -10000, refundIds: [2] }),
                tx(2, {
                    amount: 2400,
                    categoryId: 2,
                    accountId: 1,
                    refundOfId: 1,
                }),
            ],
        });
        const { user } = renderUI(<TransactionsPage />);
        const row = screen.getByText("tx 2").closest("tr");
        const categorySelect = row.querySelectorAll("button.gsel")[1];

        await user.click(categorySelect);

        const food = screen.getByRole("option", { name: "Food", hidden: true });
        const dropdown = food.closest(".gsel__drop");
        expect(food).toBeInTheDocument();
        expect(
            within(dropdown).queryByRole("option", { name: "Salary", hidden: true }),
        ).not.toBeInTheDocument();
        await user.click(categorySelect);
        await waitFor(() => expect(food).not.toBeInTheDocument());
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

    it("opens amount range filter dropdown", async () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                tx(1, { description: "Cheap item", amount: -50_00, date: "2026-03-01" }),
                tx(2, { description: "Mid item", amount: -500_00, date: "2026-03-02" }),
                tx(3, { description: "Expensive item", amount: -5000_00, date: "2026-03-03" }),
            ],
        });
        const { user, container } = renderUI(<TransactionsPage />);
        expect(screen.getByText("3 transactions")).toBeInTheDocument();
        const toolbar = container.querySelector(".budget-toolbar");
        await user.click(within(toolbar).getByRole("button", { name: "Amount" }));
        expect(screen.getAllByRole("slider")).toHaveLength(2);
    });

    it("shows hidden rows when the toggle is active", async () => {
        resetStore();
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                {
                    id: 1,
                    date: "2026-03-01T00:00:00",
                    amount: -1000,
                    description: "Visible",
                    bankCategory: "",
                    mcc: "",
                    categoryId: 2,
                    accountId: 1,
                    transferId: null,
                    comment: "",
                    source: "manual",
                    hidden: false,
                },
                {
                    id: 2,
                    date: "2026-03-02T00:00:00",
                    amount: -1000,
                    description: "Hidden tx",
                    bankCategory: "",
                    mcc: "",
                    categoryId: 2,
                    accountId: 1,
                    transferId: null,
                    comment: "",
                    source: "manual",
                    hidden: true,
                },
            ],
        });
        const { user } = renderUI(<TransactionsPage />);
        expect(screen.getByText("Visible")).toBeInTheDocument();
        const hiddenRowEl = screen.queryByText("Hidden tx");
        expect(hiddenRowEl).not.toBeNull();
        expect(hiddenRowEl.closest("tr")).toHaveClass("tx-hidden-row");

        await user.click(screen.getByRole("button", { name: "Hidden" }));

        expect(screen.getByText("Visible")).toBeInTheDocument();
        expect(screen.getByText("Hidden tx")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Hidden" })).toHaveAttribute(
            "aria-pressed",
            "true",
        );
    });

    it("expands a split transaction and shows its parts", async () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                tx(1, {
                    description: "Split purchase",
                    splits: [
                        { id: 10, categoryId: 2, amount: -500_00 },
                        { id: 11, categoryId: 3, amount: -300_00 },
                    ],
                    date: "2026-03-01",
                }),
            ],
        });
        const { user } = renderUI(<TransactionsPage />);
        await user.click(screen.getByRole("button", { name: /split · 2/i }));

        const rows = screen.getAllByRole("row").filter((r) => r.classList.contains("cat-row"));
        const parentRow = rows.find((r) => r.classList.contains("tx-row_leg"));
        expect(parentRow).toBeInTheDocument();
        expect(parentRow).toHaveTextContent("Food");
    });

    it("renders an uncategorized transaction and allows clearing the category", async () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                tx(1, { description: "Mystery charge", categoryId: null, date: "2026-03-01" }),
            ],
        });
        const setTxCategory = vi.spyOn(useStore.getState(), "setTxCategory").mockResolvedValue();
        const { user } = renderUI(<TransactionsPage />);
        const row = screen.getByText("Mystery charge").closest("tr");
        const selects = row.querySelectorAll("button.gsel");
        await user.click(selects[1]);
        await user.click(screen.getByRole("option", { name: "Leave uncategorized", hidden: true }));
        await waitFor(() => expect(setTxCategory).toHaveBeenCalledWith(1, null));
    });

    it("shows bank category in the ledger column", () => {
        seed({
            transactions: [
                tx(1, {
                    description: "Purchase",
                    bankCategory: "Retail Shopping",
                    date: "2026-03-01",
                }),
            ],
        });
        renderUI(<TransactionsPage />);
        expect(screen.getByText("Retail Shopping")).toBeInTheDocument();
    });

    it("shows the split indicator on a split transaction row", () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                tx(1, {
                    description: "Split purchase",
                    splits: [{ id: 10, categoryId: 2, amount: -500_00 }],
                    date: "2026-03-01",
                }),
            ],
        });
        renderUI(<TransactionsPage />);
        expect(screen.getByRole("button", { name: /split · 1/i })).toBeInTheDocument();
    });

    it("renders transactions with correct date formatting", () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                {
                    id: 1,
                    date: "2026-03-01T00:00:00",
                    amount: -1000,
                    description: "First",
                    bankCategory: "",
                    mcc: "",
                    categoryId: 2,
                    accountId: 1,
                    transferId: null,
                    comment: "",
                    source: "manual",
                },
                {
                    id: 2,
                    date: "2026-02-01T00:00:00",
                    amount: -1000,
                    description: "Second",
                    bankCategory: "",
                    mcc: "",
                    categoryId: 2,
                    accountId: 1,
                    transferId: null,
                    comment: "",
                    source: "manual",
                },
            ],
        });
        renderUI(<TransactionsPage />);
        expect(screen.getByText("First")).toBeInTheDocument();
        expect(screen.getByText("Second")).toBeInTheDocument();
    });

    it("renders income transactions with money_pos class", () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [tx(1, { description: "Income", amount: 5000_00, date: "2026-03-01" })],
        });
        renderUI(<TransactionsPage />);
        const row = screen.getByText("Income").closest("tr");
        const moneyEl = row.querySelector(".money");
        expect(moneyEl).toHaveClass("money_pos");
    });

    it("shows zero-amount rows without crashing", () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [tx(1, { description: "Zero item", amount: 0, date: "2026-03-01" })],
        });
        renderUI(<TransactionsPage />);
        expect(screen.getByText("Zero item")).toBeInTheDocument();
        expect(screen.getByText("0 ₽")).toBeInTheDocument();
    });

    it("offers only income categories for a positive row", async () => {
        seed({
            accounts,
            groups: [
                { id: 1, name: "Income", kind: "income", sort: 1 },
                { id: 2, name: "Spending", kind: "expense", sort: 2 },
            ],
            categories: [
                { id: 1, groupId: 1, name: "Salary", archived: false },
                { id: 2, groupId: 2, name: "Food", archived: false },
            ],
            transactions: [
                tx(1, { description: "Income tx", amount: 1000_00, date: "2026-03-01" }),
            ],
        });
        const { user } = renderUI(<TransactionsPage />);
        const row = screen.getByText("Income tx").closest("tr");
        const selects = row.querySelectorAll("button.gsel");

        await user.click(selects[1]);

        const salary = screen.getByRole("option", { name: "Salary", hidden: true });
        const dropdown = salary.closest(".gsel__drop");
        expect(salary).toBeInTheDocument();
        expect(
            within(dropdown).queryByRole("option", { name: "Food", hidden: true }),
        ).not.toBeInTheDocument();
    });

    it("hides the back-to-top button until the page is scrolled", () => {
        seed({ transactions: [tx(1, { description: "Item", date: "2026-03-01" })] });
        renderUI(<TransactionsPage />);
        expect(screen.queryByRole("button", { name: "Back to top" })).not.toBeInTheDocument();
    });

    it("renders a transfer as a single merged row with no per-row action menu", () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [
                {
                    id: 1,
                    date: "2026-03-01T00:00:00",
                    amount: -1000,
                    description: "Out",
                    bankCategory: "",
                    mcc: "",
                    categoryId: 2,
                    accountId: 1,
                    transferId: 55,
                    comment: "",
                    source: "manual",
                },
                {
                    id: 2,
                    date: "2026-03-01T00:00:00",
                    amount: 1000,
                    description: "In",
                    bankCategory: "",
                    mcc: "",
                    categoryId: 2,
                    accountId: 2,
                    transferId: 55,
                    comment: "",
                    source: "manual",
                },
            ],
        });
        renderUI(<TransactionsPage />);
        expect(
            screen.getByText("Transfer", { selector: "span.tx-transfer__label" }),
        ).toBeInTheDocument();
        expect(
            screen.queryByRole("button", { name: "Transaction actions" }),
        ).not.toBeInTheDocument();
    });

    it("shows the delete button for an editable row", () => {
        seed({
            accounts,
            groups,
            categories,
            transactions: [tx(1, { description: "Deletable", date: "2026-03-01" })],
        });
        renderUI(<TransactionsPage />);
        const row = screen.getByText("Deletable").closest("tr");
        expect(row.querySelector('[aria-label="Transaction actions"]')).toBeInTheDocument();
    });
});
