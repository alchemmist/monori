import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminPage from "./AdminPage.jsx";
import { renderUI, screen, waitFor, userEvent } from "../test/render.jsx";
import { useStore } from "../store.js";

vi.mock("../api.js");

const mockApi = vi.hoisted(() => ({
    adminOverview: vi.fn(),
    adminUsers: vi.fn(),
    adminActivity: vi.fn(),
    adminUserDetail: vi.fn(),
    adminDeleteUser: vi.fn(),
}));

vi.doMock("../api.js", () => ({
    api: mockApi,
}));

describe("AdminPage", () => {
    const mockOverview = {
        totals: {
            users: 150,
            transactions: 5000,
            accounts: 200,
            connections: 30,
        },
        activeUsers7d: 45,
        newUsers7d: 12,
        newUsers30d: 35,
        dbSizeBytes: 52428800,
        registrations: [{ month: "2026-01", count: 10 }, { month: "2026-02", count: 15 }],
    };

    const mockUsers = [
        {
            id: 1,
            email: "alice@example.com",
            isAdmin: false,
            createdAt: "2026-01-01",
            lastLogin: "2026-03-10T14:30:00",
            accounts: 2,
            transactions: 100,
            budgets: 3,
            lastTransaction: "2026-03-10",
            connection: { status: "connected", lastSync: "2026-03-10", lastError: null },
        },
        {
            id: 2,
            email: "bob@example.com",
            isAdmin: true,
            createdAt: "2026-01-05",
            lastLogin: "2026-03-11T10:00:00",
            accounts: 1,
            transactions: 50,
            budgets: 1,
            lastTransaction: "2026-03-09",
            connection: { status: "error", lastSync: "2026-03-10", lastError: "Auth failed" },
        },
    ];

    const mockActivity = {
        daily: [
            { day: "2026-02-09", count: 50 },
            { day: "2026-02-10", count: 60 },
        ],
        features: [
            { feature: "import", count: 120 },
            { feature: "sync", count: 80 },
        ],
        recentLogins: [
            { email: "alice@example.com", at: "2026-03-11T15:30:00" },
            { email: "bob@example.com", at: "2026-03-11T14:00:00" },
        ],
    };

    beforeEach(() => {
        vi.clearAllMocks();
        globalThis.localStorage?.clear?.();
        mockApi.adminOverview.mockResolvedValue(mockOverview);
        mockApi.adminUsers.mockResolvedValue(mockUsers);
        mockApi.adminActivity.mockResolvedValue(mockActivity);
    });

    it("renders admin page title", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("Admin")).toBeInTheDocument();
        });
    });

    it("loads data on mount", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(mockApi.adminOverview).toHaveBeenCalled();
            expect(mockApi.adminUsers).toHaveBeenCalled();
            expect(mockApi.adminActivity).toHaveBeenCalled();
        });
    });

    it("displays error when data load fails", async () => {
        mockApi.adminOverview.mockRejectedValueOnce(new Error("API error"));
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText(/Failed to load admin data/)).toBeInTheDocument();
        });
    });

    it("does not render until all data is loaded", () => {
        mockApi.adminOverview.mockImplementation(
            () =>
                new Promise((resolve) => {
                    setTimeout(() => resolve(mockOverview), 100);
                }),
        );
        renderUI(<AdminPage />);
        expect(screen.queryByText("Users")).not.toBeInTheDocument();
    });

    it("displays KPI cards", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("Users")).toBeInTheDocument();
            expect(screen.getByText("150")).toBeInTheDocument();
            expect(screen.getByText("Active users")).toBeInTheDocument();
            expect(screen.getByText("45")).toBeInTheDocument();
        });
    });

    it("formats user count KPI", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("+35 in 30 days")).toBeInTheDocument();
        });
    });

    it("formats active users KPI", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("Active users")).toBeInTheDocument();
            expect(screen.getByText("last 7 days")).toBeInTheDocument();
        });
    });

    it("formats transaction count with locale", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText(/5[,.]000/)).toBeInTheDocument();
        });
    });

    it("formats database size in bytes", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText(/50/)).toBeInTheDocument();
            expect(screen.getByText(/MB/)).toBeInTheDocument();
        });
    });

    it("displays users table", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
            expect(screen.getByText("bob@example.com")).toBeInTheDocument();
        });
    });

    it("displays admin badge for admin users", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            const bobRow = screen.getByText("bob@example.com").closest("tr");
            expect(bobRow).toHaveTextContent("admin");
        });
    });

    it("does not display delete button for admin users", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("bob@example.com")).toBeInTheDocument();
        });
        const bobRow = screen.getByText("bob@example.com").closest("tr");
        expect(bobRow.querySelector("button")).not.toHaveTextContent("Delete");
    });

    it("displays delete button for non-admin users", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        expect(aliceRow.querySelector("button")).toHaveTextContent("Delete");
    });

    it("opens user detail when row is clicked", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [{ id: 1, name: "Card", transactions: 50, balance: 100000 }],
            featureUsage: [{ feature: "import", count: 10 }],
            recentLogins: ["2026-03-10T14:30:00"],
            recentTransactions: [
                {
                    id: 1,
                    date: "2026-03-10",
                    description: "Coffee",
                    category: "Food",
                    account: "Card",
                    amount: -500,
                },
            ],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("Accounts")).toBeInTheDocument();
        });
    });

    it("closes user detail when row is clicked again", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("Accounts")).toBeInTheDocument();
        });
        await user.click(aliceRow);
        expect(screen.queryByText("Accounts")).not.toBeInTheDocument();
    });

    it("displays user detail accounts", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [
                { id: 1, name: "Card", transactions: 50, balance: 100000 },
                { id: 2, name: "Bank", transactions: 25, balance: 500000 },
            ],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("Card")).toBeInTheDocument();
            expect(screen.getByText("Bank")).toBeInTheDocument();
        });
    });

    it("displays empty accounts message", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("No accounts")).toBeInTheDocument();
        });
    });

    it("displays feature usage", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [
                { feature: "import", count: 10 },
                { feature: "sync", count: 5 },
            ],
            recentLogins: [],
            recentTransactions: [],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("import")).toBeInTheDocument();
            expect(screen.getByText("sync")).toBeInTheDocument();
        });
    });

    it("displays empty feature usage message", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("No API activity")).toBeInTheDocument();
        });
    });

    it("displays recent logins", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [],
            recentLogins: [
                "2026-03-11T15:30:00",
                "2026-03-10T14:00:00",
                "2026-03-09T10:30:00",
            ],
            recentTransactions: [],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("2026-03-11 15:30")).toBeInTheDocument();
        });
    });

    it("displays empty logins message", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("Never logged in")).toBeInTheDocument();
        });
    });

    it("displays recent transactions", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [
                {
                    id: 1,
                    date: "2026-03-10",
                    description: "Coffee",
                    category: "Food",
                    account: "Card",
                    amount: -500,
                },
                {
                    id: 2,
                    date: "2026-03-09",
                    description: "Salary",
                    category: "Income",
                    account: "Bank",
                    amount: 100000,
                },
            ],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("Coffee")).toBeInTheDocument();
            expect(screen.getByText("Salary")).toBeInTheDocument();
        });
    });

    it("displays empty transactions message", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [],
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("No transactions")).toBeInTheDocument();
        });
    });

    it("arms delete confirmation on first click", async () => {
        const { user } = renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        const deleteButton = aliceRow.querySelector("button");
        await user.click(deleteButton);
        expect(screen.getByText("Sure?")).toBeInTheDocument();
    });

    it("executes delete on confirmation", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminDeleteUser.mockResolvedValueOnce({});
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        const deleteButton = aliceRow.querySelector("button");
        await user.click(deleteButton);
        expect(screen.getByText("Sure?")).toBeInTheDocument();
        await user.click(deleteButton);
        await waitFor(() => {
            expect(mockApi.adminDeleteUser).toHaveBeenCalledWith(1);
        });
    });

    it("shows error toast on delete failure", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminDeleteUser.mockRejectedValueOnce(new Error("Delete failed"));
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        const deleteButton = aliceRow.querySelector("button");
        await user.click(deleteButton);
        await user.click(deleteButton);
        await waitFor(() => {
            expect(screen.getByText("Delete failed")).toBeInTheDocument();
        });
    });

    it("reloads data after successful delete", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminDeleteUser.mockResolvedValueOnce({});
        mockApi.adminOverview.mockClear();
        mockApi.adminUsers.mockClear();
        mockApi.adminActivity.mockClear();
        mockApi.adminOverview.mockResolvedValue(mockOverview);
        mockApi.adminUsers.mockResolvedValue(mockUsers);
        mockApi.adminActivity.mockResolvedValue(mockActivity);
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        const deleteButton = aliceRow.querySelector("button");
        await user.click(deleteButton);
        await user.click(deleteButton);
        await waitFor(() => {
            expect(mockApi.adminOverview).toHaveBeenCalledTimes(2);
        });
    });

    it("closes detail on user delete", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [],
        });
        mockApi.adminDeleteUser.mockResolvedValueOnce({});
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("Accounts")).toBeInTheDocument();
        });
        const deleteButton = aliceRow.querySelector("button");
        await user.click(deleteButton);
        await user.click(deleteButton);
        await waitFor(() => {
            expect(screen.queryByText("Accounts")).not.toBeInTheDocument();
        });
    });

    it("refreshes detail when adminTick is bumped", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail
            .mockResolvedValueOnce({
                user: mockUsers[0],
                accounts: [{ id: 1, name: "Card", transactions: 50, balance: 100000 }],
                featureUsage: [],
                recentLogins: [],
                recentTransactions: [],
            })
            .mockResolvedValueOnce({
                user: mockUsers[0],
                accounts: [
                    { id: 1, name: "Card", transactions: 51, balance: 100500 },
                    { id: 2, name: "Bank", transactions: 1, balance: 50000 },
                ],
                featureUsage: [],
                recentLogins: [],
                recentTransactions: [],
            });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("Card")).toBeInTheDocument();
        });
        useStore.getState().bumpAdminTick();
        await waitFor(() => {
            expect(mockApi.adminUserDetail).toHaveBeenCalledTimes(2);
        });
    });

    it("closes detail if refresh fails", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail
            .mockResolvedValueOnce({
                user: mockUsers[0],
                accounts: [],
                featureUsage: [],
                recentLogins: [],
                recentTransactions: [],
            })
            .mockRejectedValueOnce(new Error("Load failed"));
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("Accounts")).toBeInTheDocument();
        });
        useStore.getState().bumpAdminTick();
        await waitFor(() => {
            expect(screen.queryByText("Accounts")).not.toBeInTheDocument();
        });
    });

    it("displays SQL console button", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByRole("button", { name: "SQL console" })).toBeInTheDocument();
        });
    });

    it("displays sync badge with status", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("connected")).toBeInTheDocument();
        });
    });

    it("displays sync badge with last sync date", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText(/2026-03-10/)).toBeInTheDocument();
        });
    });

    it("displays error sync badge in red", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("error")).toBeInTheDocument();
        });
    });

    it("displays recent logins in activity card", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
    });

    it("shows empty recent logins message", async () => {
        mockApi.adminActivity.mockResolvedValueOnce({
            daily: [],
            features: [],
            recentLogins: [],
        });
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("No logins yet")).toBeInTheDocument();
        });
    });

    it("formats transaction count with thousand separators", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText(/5[,.]000/)).toBeInTheDocument();
        });
    });

    it("clears armed delete state when mouse leaves user row", async () => {
        const { user } = renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        const deleteButton = aliceRow.querySelector("button");
        await user.click(deleteButton);
        expect(screen.getByText("Sure?")).toBeInTheDocument();
        await user.pointer({ keys: "[MouseOut]", target: aliceRow });
        await waitFor(() => {
            expect(screen.queryByText("Sure?")).not.toBeInTheDocument();
        });
    });

    it("displays registered date for user", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("2026-01-01")).toBeInTheDocument();
        });
    });

    it("displays last login timestamp", async () => {
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText(/2026-03-10 14:30|2026-03-11 10:00/)).toBeInTheDocument();
        });
    });

    it("displays null date as dash", async () => {
        const userWithoutLogin = {
            ...mockUsers[0],
            lastLogin: null,
            lastTransaction: null,
        };
        mockApi.adminUsers.mockResolvedValueOnce([userWithoutLogin]);
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        expect(aliceRow).toHaveTextContent("—");
    });

    it("limits recent logins display to 12 items", async () => {
        const manyLogins = Array.from({ length: 20 }, (_, i) => ({
            email: `user${i}@example.com`,
            at: `2026-03-${String(i + 1).padStart(2, "0")}T10:00:00`,
        }));
        mockApi.adminActivity.mockResolvedValueOnce({
            daily: [],
            features: [],
            recentLogins: manyLogins,
        });
        renderUI(<AdminPage />);
        await waitFor(() => {
            expect(screen.getByText("user0@example.com")).toBeInTheDocument();
            expect(screen.queryByText("user19@example.com")).not.toBeInTheDocument();
        });
    });

    it("limits recent transactions display to 5 items", async () => {
        const { user } = renderUI(<AdminPage />);
        mockApi.adminUserDetail.mockResolvedValueOnce({
            user: mockUsers[0],
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: Array.from({ length: 10 }, (_, i) => ({
                id: i + 1,
                date: "2026-03-10",
                description: `tx ${i + 1}`,
                category: "Food",
                account: "Card",
                amount: -500,
            })),
        });
        await waitFor(() => {
            expect(screen.getByText("alice@example.com")).toBeInTheDocument();
        });
        const aliceRow = screen.getByText("alice@example.com").closest("tr");
        await user.click(aliceRow);
        await waitFor(() => {
            expect(screen.getByText("tx 1")).toBeInTheDocument();
            expect(screen.queryByText("tx 6")).not.toBeInTheDocument();
        });
    });
});
