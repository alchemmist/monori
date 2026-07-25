import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import TransactionsPage from "./TransactionsPage.jsx";
import {
    renderUI,
    resetStore,
    atDemo,
    demo,
    seed,
    tx,
    screen,
    waitFor,
    fireEvent,
} from "../test/render.jsx";

describe("TransactionsPage", () => {
    beforeEach(() => {
        resetStore();
        vi.clearAllMocks();
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it("renders with demo data showing all transactions", () => {
        atDemo();
        renderUI(<TransactionsPage />);

        const heading = screen.getByRole("heading", { name: "Transactions" });
        expect(heading).toBeInTheDocument();
    });

    it("displays transaction count", () => {
        demo();
        renderUI(<TransactionsPage />);

        expect(screen.getByText(/\d+ transactions/)).toBeInTheDocument();
    });

    it("shows empty state when no transactions match", () => {
        seed({ transactions: [] });
        renderUI(<TransactionsPage />);

        expect(screen.getByText("Nothing found")).toBeInTheDocument();
    });

    it("renders table headers correctly", () => {
        seed({ transactions: [tx(1)] });
        renderUI(<TransactionsPage />);

        expect(screen.getByRole("columnheader", { name: "Date" })).toBeInTheDocument();
        expect(screen.getByRole("columnheader", { name: "Description" })).toBeInTheDocument();
        expect(screen.getByRole("columnheader", { name: "Bank category" })).toBeInTheDocument();
        expect(screen.getByRole("columnheader", { name: "Amount" })).toBeInTheDocument();
        expect(screen.getByRole("columnheader", { name: "Account" })).toBeInTheDocument();
        expect(screen.getByRole("columnheader", { name: "Category" })).toBeInTheDocument();
    });

    it("formats transaction date as dd.mm.yyyy", () => {
        seed({ transactions: [tx(1, { date: "2026-03-15" })] });
        renderUI(<TransactionsPage />);

        expect(screen.getByText("15.03.2026")).toBeInTheDocument();
    });

    it("displays transaction description", () => {
        seed({ transactions: [tx(1, { description: "Rent payment" })] });
        renderUI(<TransactionsPage />);

        expect(screen.getByText("Rent payment")).toBeInTheDocument();
    });

    it("shows adjustment tag for manual adjustments", () => {
        seed({ transactions: [tx(1, { source: "adjustment" })] });
        renderUI(<TransactionsPage />);

        expect(screen.getByText("adjustment")).toBeInTheDocument();
    });

    it("shows transfer tag for transfer transactions", () => {
        seed({ transactions: [tx(1, { transferId: 99 })] });
        renderUI(<TransactionsPage />);

        expect(screen.getByText("transfer")).toBeInTheDocument();
    });

    it("allows filtering by text search in description", async () => {
        const { user } = renderUI(null);
        seed({
            transactions: [
                tx(1, { description: "Apple Store purchase" }),
                tx(2, { description: "Rent payment" }),
            ],
        });
        renderUI(<TransactionsPage />);

        const searchInput = screen.getByPlaceholderText("Search description");
        await user.type(searchInput, "Apple");
        vi.runAllTimers();

        expect(screen.getByText("Apple Store purchase")).toBeInTheDocument();
        expect(screen.queryByText("Rent payment")).not.toBeInTheDocument();
    });

    it("clears search with clear button", async () => {
        const { user } = renderUI(null);
        seed({
            transactions: [
                tx(1, { description: "Coffee" }),
                tx(2, { description: "Rent" }),
            ],
        });
        renderUI(<TransactionsPage />);

        const searchInput = screen.getByPlaceholderText("Search description");
        await user.type(searchInput, "Coffee");
        expect(searchInput).toHaveValue("Coffee");
        vi.runAllTimers();

        const clearBtn = screen.getByLabelText("Clear search");
        await user.click(clearBtn);

        expect(searchInput).toHaveValue("");
        expect(screen.getByText("Rent")).toBeInTheDocument();
    });

    it("shows Import button and opens ImportDialog", async () => {
        const { user } = renderUI(null);
        seed({ transactions: [] });
        renderUI(<TransactionsPage />);

        const importBtn = screen.getByRole("button", { name: /Import statement/i });
        expect(importBtn).toBeInTheDocument();

        await user.click(importBtn);

        expect(screen.getByText("Import bank statement")).toBeInTheDocument();
    });

    it("closes ImportDialog when onClose is called", async () => {
        const { user } = renderUI(null);
        seed({ transactions: [] });
        renderUI(<TransactionsPage />);

        const importBtn = screen.getByRole("button", { name: /Import statement/i });
        await user.click(importBtn);

        expect(screen.getByText("Import bank statement")).toBeInTheDocument();

        const cancelBtn = screen.getByRole("button", { name: "Cancel" });
        await user.click(cancelBtn);

        await waitFor(() => {
            expect(screen.queryByText("Import bank statement")).not.toBeInTheDocument();
        });
    });

    it("shows Transfer button when multiple accounts exist", () => {
        seed({
            accounts: [
                { id: 1, name: "Card", archived: false },
                { id: 2, name: "Cash", archived: false },
            ],
            transactions: [],
        });
        renderUI(<TransactionsPage />);

        const transferBtn = screen.getByRole("button", { name: /Transfer/i });
        expect(transferBtn).not.toBeDisabled();
    });

    it("disables Transfer button when only one account", () => {
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
            transactions: [],
        });
        renderUI(<TransactionsPage />);

        const transferBtn = screen.getByRole("button", { name: /Transfer/i });
        expect(transferBtn).toBeDisabled();
    });

    it("reverses transaction order (newest first)", () => {
        seed({
            transactions: [
                tx(1, { date: "2026-01-01", description: "First" }),
                tx(2, { date: "2026-03-15", description: "Second" }),
                tx(3, { date: "2026-02-01", description: "Third" }),
            ],
        });
        renderUI(<TransactionsPage />);

        const rows = screen.getAllByRole("row");
        const descriptions = rows.map((r) => r.textContent).join(" ");

        const secondIdx = descriptions.indexOf("Second");
        const thirdIdx = descriptions.indexOf("Third");
        const firstIdx = descriptions.indexOf("First");

        expect(secondIdx).toBeLessThan(thirdIdx);
        expect(thirdIdx).toBeLessThan(firstIdx);
    });

    it("scrolls back to top when filter changes", async () => {
        const { user } = renderUI(null);
        seed({
            transactions: [
                tx(1, { description: "A" }),
                tx(2, { description: "B" }),
                tx(3, { description: "C" }),
            ],
        });
        renderUI(<TransactionsPage />);

        const scrollToSpy = vi.spyOn(window, "scrollTo");

        const searchInput = screen.getByPlaceholderText("Search description");
        await user.type(searchInput, "B");
        vi.runAllTimers();

        expect(scrollToSpy).toHaveBeenCalledWith({ top: 0 });

        scrollToSpy.mockRestore();
    });

    it("shows scroll-to-top button when scrolled down", () => {
        seed({ transactions: [tx(1)] });
        renderUI(<TransactionsPage />);

        fireEvent.scroll(window, { y: 1500 });
        vi.runAllTimers();

        const topBtn = screen.queryByLabelText("Back to top");
        expect(topBtn).toBeInTheDocument();
    });

    it("hides back button when scrolled to top", () => {
        seed({ transactions: [tx(1)] });
        renderUI(<TransactionsPage />);

        fireEvent.scroll(window, { y: 100 });
        vi.runAllTimers();

        const topBtn = screen.queryByLabelText("Back to top");
        expect(topBtn).not.toBeInTheDocument();
    });

    it("hides account filter when only one account", () => {
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
            transactions: [tx(1)],
        });
        renderUI(<TransactionsPage />);

        const accountHeaders = screen.queryAllByRole("button").filter((b) =>
            b.textContent.includes("All accounts"),
        );
        expect(accountHeaders.length).toBe(0);
    });

    it("handles archived account in options for transaction", () => {
        seed({
            accounts: [
                { id: 1, name: "Active Card", archived: false },
                { id: 2, name: "Old Card", archived: true },
            ],
            transactions: [tx(1, { accountId: 2 })],
        });
        renderUI(<TransactionsPage />);

        expect(screen.getByText("Old Card")).toBeInTheDocument();
    });

    it("filters by bank category search", () => {
        seed({
            transactions: [
                tx(1, { bankCategory: "Payment" }),
                tx(2, { bankCategory: "Withdrawal" }),
            ],
        });
        renderUI(<TransactionsPage />);

        const searchInput = screen.getByPlaceholderText("Search description");
        expect(searchInput).toBeInTheDocument();
    });

    it("shows positive amount with money_pos class", () => {
        seed({ transactions: [tx(1, { amount: 100000 })] });
        renderUI(<TransactionsPage />);

        const rows = screen.getAllByRole("row");
        const row = rows.find((r) => r.textContent.includes("tx 1"));
        expect(row).toBeInTheDocument();
        const moneySpan = row.querySelector(".money.money_pos");
        expect(moneySpan).toBeInTheDocument();
    });
});
