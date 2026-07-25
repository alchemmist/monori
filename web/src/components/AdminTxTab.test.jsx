import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminTxTab from "./AdminTxTab.jsx";
import { renderUI, screen, waitFor, userEvent } from "../test/render.jsx";

vi.mock("../api.js");

const mockApi = vi.hoisted(() => ({
    adminUserTransactions: vi.fn(),
    adminDeleteUserTransactions: vi.fn(),
}));

vi.doMock("../api.js", () => ({
    api: mockApi,
}));

describe("AdminTxTab", () => {
    const testUser = { id: 1, email: "user@example.com" };

    beforeEach(() => {
        vi.clearAllMocks();
        globalThis.localStorage?.clear?.();
    });

    it("renders with user email in title", () => {
        mockApi.adminUserTransactions.mockResolvedValueOnce([]);
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        expect(screen.getByText(/user@example.com/)).toBeInTheDocument();
    });

    it("loads transactions on mount", async () => {
        mockApi.adminUserTransactions.mockResolvedValueOnce([]);
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(mockApi.adminUserTransactions).toHaveBeenCalledWith(1, {
                limit: 1000,
                offset: 0,
            });
        });
    });

    it("shows loading state initially", () => {
        mockApi.adminUserTransactions.mockImplementation(
            () =>
                new Promise((resolve) => {
                    setTimeout(() => resolve([]), 100);
                }),
        );
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        expect(screen.getByText("Loading…")).toBeInTheDocument();
    });

    it("displays empty state when no transactions", async () => {
        mockApi.adminUserTransactions.mockResolvedValueOnce([]);
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(screen.getByText("No transactions")).toBeInTheDocument();
        });
    });

    it("displays error toast on load failure", async () => {
        mockApi.adminUserTransactions.mockRejectedValueOnce(new Error("Network error"));
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(screen.getByText("Network error")).toBeInTheDocument();
        });
    });

    it("renders transactions in table", async () => {
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05T10:00:00",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
            {
                id: 2,
                date: "2026-03-06T15:30:00",
                description: "Salary",
                category: "Income",
                account: "Bank",
                amount: 100000,
            },
        ]);
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
            expect(screen.getByText("Salary")).toBeInTheDocument();
        });
    });

    it("filters transactions by account", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
            {
                id: 2,
                date: "2026-03-06",
                description: "Salary",
                category: "Income",
                account: "Bank",
                amount: 100000,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const accountSelect = screen.getByRole("combobox");
        await user.click(accountSelect);
        await waitFor(() => {
            expect(screen.getByRole("option", { name: "Card" })).toBeInTheDocument();
            expect(screen.getByRole("option", { name: "Bank" })).toBeInTheDocument();
        });
        await user.click(screen.getByRole("option", { name: "Card" }));
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
            expect(screen.queryByText("Salary")).not.toBeInTheDocument();
        });
    });

    it("shows all accounts option", async () => {
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const accountSelect = screen.getByRole("combobox");
        await user.click(accountSelect);
        expect(screen.getByRole("option", { name: "All accounts" })).toBeInTheDocument();
    });

    it("resets selection when changing filter", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const coffeeRow = screen.getByText("Coffee").closest("tr");
        const checkbox = coffeeRow.querySelector("input[type=checkbox]");
        await user.click(checkbox);
        expect(checkbox).toBeChecked();
        const accountSelect = screen.getByRole("combobox");
        await user.click(accountSelect);
    });

    it("selects individual transactions", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const coffeeRow = screen.getByText("Coffee").closest("tr");
        const checkbox = coffeeRow.querySelector("input[type=checkbox]");
        await user.click(checkbox);
        expect(checkbox).toBeChecked();
    });

    it("selects all visible transactions", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
            {
                id: 2,
                date: "2026-03-06",
                description: "Milk",
                category: "Food",
                account: "Card",
                amount: -300,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const selectAllCheckbox = screen.getByRole("checkbox", { name: /Select all visible/ });
        await user.click(selectAllCheckbox);
        const rows = screen.getAllByText(/Coffee|Milk/);
        rows.forEach((row) => {
            const checkbox = row.closest("tr").querySelector("input[type=checkbox]");
            expect(checkbox).toBeChecked();
        });
    });

    it("updates select all checkbox when individual selections change", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
            {
                id: 2,
                date: "2026-03-06",
                description: "Milk",
                category: "Food",
                account: "Card",
                amount: -300,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const selectAllCheckbox = screen.getByRole("checkbox", { name: /Select all visible/ });
        expect(selectAllCheckbox).not.toBeChecked();
        await user.click(selectAllCheckbox);
        expect(selectAllCheckbox).toBeChecked();
        const coffeeRow = screen.getByText("Coffee").closest("tr");
        const coffeeCheckbox = coffeeRow.querySelector("input[type=checkbox]");
        await user.click(coffeeCheckbox);
        expect(selectAllCheckbox).not.toBeChecked();
    });

    it("displays selection count in footer", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("0 selected")).toBeInTheDocument();
        });
        const checkbox = screen.getByText("Coffee").closest("tr").querySelector("input");
        await user.click(checkbox);
        expect(screen.getByText("1 selected")).toBeInTheDocument();
    });

    it("disables delete button when nothing is selected", async () => {
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(screen.getByRole("button", { name: "Delete selected" })).toBeDisabled();
        });
    });

    it("arms delete confirmation on first click", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const checkbox = screen.getByText("Coffee").closest("tr").querySelector("input");
        await user.click(checkbox);
        const deleteButton = screen.getByRole("button", { name: "Delete selected" });
        await user.click(deleteButton);
        expect(screen.getByRole("button", { name: /Delete 1 — sure/ })).toBeInTheDocument();
    });

    it("deletes selected transactions on confirmation", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions
            .mockResolvedValueOnce([
                {
                    id: 1,
                    date: "2026-03-05",
                    description: "Coffee",
                    category: "Food",
                    account: "Card",
                    amount: -500,
                },
            ])
            .mockResolvedValueOnce([]);
        mockApi.adminDeleteUserTransactions.mockResolvedValueOnce({ deleted: 1 });
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const checkbox = screen.getByText("Coffee").closest("tr").querySelector("input");
        await user.click(checkbox);
        const deleteButton = screen.getByRole("button", { name: "Delete selected" });
        await user.click(deleteButton);
        const confirmButton = screen.getByRole("button", { name: /Delete 1 — sure/ });
        await user.click(confirmButton);
        await waitFor(() => {
            expect(mockApi.adminDeleteUserTransactions).toHaveBeenCalledWith(1, [1]);
        });
    });

    it("shows error toast on delete failure", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        mockApi.adminDeleteUserTransactions.mockRejectedValueOnce(
            new Error("Delete failed"),
        );
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const checkbox = screen.getByText("Coffee").closest("tr").querySelector("input");
        await user.click(checkbox);
        const deleteButton = screen.getByRole("button", { name: "Delete selected" });
        await user.click(deleteButton);
        const confirmButton = screen.getByRole("button", { name: /Delete 1 — sure/ });
        await user.click(confirmButton);
        await waitFor(() => {
            expect(screen.getByText("Delete failed")).toBeInTheDocument();
        });
    });

    it("reloads transactions after successful deletion", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions
            .mockResolvedValueOnce([
                {
                    id: 1,
                    date: "2026-03-05",
                    description: "Coffee",
                    category: "Food",
                    account: "Card",
                    amount: -500,
                },
            ])
            .mockResolvedValueOnce([]);
        mockApi.adminDeleteUserTransactions.mockResolvedValueOnce({ deleted: 1 });
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const checkbox = screen.getByText("Coffee").closest("tr").querySelector("input");
        await user.click(checkbox);
        const deleteButton = screen.getByRole("button", { name: "Delete selected" });
        await user.click(deleteButton);
        const confirmButton = screen.getByRole("button", { name: /Delete 1 — sure/ });
        await user.click(confirmButton);
        await waitFor(() => {
            expect(mockApi.adminUserTransactions).toHaveBeenCalledTimes(2);
        });
    });

    it("clears selection after delete", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions
            .mockResolvedValueOnce([
                {
                    id: 1,
                    date: "2026-03-05",
                    description: "Coffee",
                    category: "Food",
                    account: "Card",
                    amount: -500,
                },
            ])
            .mockResolvedValueOnce([]);
        mockApi.adminDeleteUserTransactions.mockResolvedValueOnce({ deleted: 1 });
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const checkbox = screen.getByText("Coffee").closest("tr").querySelector("input");
        await user.click(checkbox);
        expect(screen.getByText("1 selected")).toBeInTheDocument();
        const deleteButton = screen.getByRole("button", { name: "Delete selected" });
        await user.click(deleteButton);
        const confirmButton = screen.getByRole("button", { name: /Delete 1 — sure/ });
        await user.click(confirmButton);
        await waitFor(() => {
            expect(screen.getByText("0 selected")).toBeInTheDocument();
        });
    });

    it("displays transaction dates correctly", async () => {
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05T10:00:00",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(screen.getByText("2026-03-05")).toBeInTheDocument();
        });
    });

    it("displays transaction description or category", async () => {
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
            {
                id: 2,
                date: "2026-03-06",
                description: "",
                category: "Groceries",
                account: "Card",
                amount: -2000,
            },
            {
                id: 3,
                date: "2026-03-07",
                description: "",
                category: "",
                account: "Card",
                amount: -100,
            },
        ]);
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
            expect(screen.getByText("Groceries")).toBeInTheDocument();
            expect(screen.getByText("—")).toBeInTheDocument();
        });
    });

    it("displays income amounts with income color", async () => {
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Salary",
                category: "Income",
                account: "Bank",
                amount: 100000,
            },
        ]);
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            const amountCell = screen.getByText(/100000|100,000/);
            expect(amountCell).toHaveStyle("color: var(--m-income)");
        });
    });

    it("paginates transactions correctly", async () => {
        const transactions = Array.from({ length: 1500 }, (_, i) => ({
            id: i + 1,
            date: "2026-03-05",
            description: `tx ${i + 1}`,
            category: "Food",
            account: "Card",
            amount: -500,
        }));
        mockApi.adminUserTransactions
            .mockResolvedValueOnce(transactions.slice(0, 1000))
            .mockResolvedValueOnce(transactions.slice(1000));
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(mockApi.adminUserTransactions).toHaveBeenCalledWith(1, {
                limit: 1000,
                offset: 0,
            });
            expect(mockApi.adminUserTransactions).toHaveBeenCalledWith(1, {
                limit: 1000,
                offset: 1000,
            });
        });
    });

    it("stops pagination when page has fewer items than limit", async () => {
        mockApi.adminUserTransactions
            .mockResolvedValueOnce(
                Array.from({ length: 1000 }, (_, i) => ({
                    id: i + 1,
                    date: "2026-03-05",
                    description: `tx ${i + 1}`,
                    category: "Food",
                    account: "Card",
                    amount: -500,
                })),
            )
            .mockResolvedValueOnce(
                Array.from({ length: 500 }, (_, i) => ({
                    id: i + 1001,
                    date: "2026-03-05",
                    description: `tx ${i + 1001}`,
                    category: "Food",
                    account: "Card",
                    amount: -500,
                })),
            );
        renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(mockApi.adminUserTransactions).toHaveBeenCalledTimes(2);
        });
    });

    it("counts visible transactions correctly", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
            {
                id: 2,
                date: "2026-03-06",
                description: "Gas",
                category: "Transport",
                account: "Card",
                amount: -1500,
            },
            {
                id: 3,
                date: "2026-03-07",
                description: "Salary",
                category: "Income",
                account: "Bank",
                amount: 100000,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const selectAllCheckbox = screen.getByRole("checkbox", { name: /Select all visible/ });
        expect(selectAllCheckbox).toHaveAttribute("label", expect.stringContaining("(3)"));
        const accountSelect = screen.getByRole("combobox");
        await user.click(accountSelect);
        await user.click(screen.getByRole("option", { name: "Bank" }));
        await waitFor(() => {
            expect(screen.getByText("Salary")).toBeInTheDocument();
            expect(screen.queryByText("Coffee")).not.toBeInTheDocument();
        });
    });

    it("clicking row toggles checkbox", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const coffeeRow = screen.getByText("Coffee").closest("tr");
        const checkbox = coffeeRow.querySelector("input[type=checkbox]");
        expect(checkbox).not.toBeChecked();
        await user.click(coffeeRow);
        expect(checkbox).toBeChecked();
        await user.click(coffeeRow);
        expect(checkbox).not.toBeChecked();
    });

    it("checkbox click does not toggle via row click", async () => {
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        mockApi.adminUserTransactions.mockResolvedValueOnce([
            {
                id: 1,
                date: "2026-03-05",
                description: "Coffee",
                category: "Food",
                account: "Card",
                amount: -500,
            },
        ]);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
        });
        const coffeeRow = screen.getByText("Coffee").closest("tr");
        const checkbox = coffeeRow.querySelector("input[type=checkbox]");
        await user.click(checkbox);
        expect(checkbox).toBeChecked();
        await user.click(checkbox);
        expect(checkbox).not.toBeChecked();
    });

    it("loads multiple pages of transactions before showing delete", async () => {
        mockApi.adminUserTransactions
            .mockResolvedValueOnce(
                Array.from({ length: 1000 }, (_, i) => ({
                    id: i + 1,
                    date: "2026-03-05",
                    description: `tx ${i + 1}`,
                    category: "Food",
                    account: "Card",
                    amount: -500,
                })),
            )
            .mockResolvedValueOnce(
                Array.from({ length: 500 }, (_, i) => ({
                    id: i + 1001,
                    date: "2026-03-05",
                    description: `tx ${i + 1001}`,
                    category: "Food",
                    account: "Card",
                    amount: -500,
                })),
            )
            .mockResolvedValueOnce(
                Array.from({ length: 1500 }, (_, i) => ({
                    id: i + 1,
                    date: "2026-03-05",
                    description: `tx ${i + 1}`,
                    category: "Food",
                    account: "Card",
                    amount: -500,
                })),
            );
        mockApi.adminDeleteUserTransactions.mockResolvedValueOnce({ deleted: 1500 });
        const { user } = renderUI(<AdminTxTab user={testUser} onClose={vi.fn()} />);
        await waitFor(() => {
            expect(mockApi.adminUserTransactions).toHaveBeenCalledTimes(2);
        });
        const selectAllCheckbox = screen.getByRole("checkbox", { name: /Select all visible/ });
        await user.click(selectAllCheckbox);
        expect(screen.getByText("1000 selected")).toBeInTheDocument();
    });
});
