import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@mantine/charts", () => ({
    AreaChart: () => <div data-testid="area-chart" />,
    BarChart: () => <div data-testid="bar-chart" />,
}));

import AdminPage from "./AdminPage.jsx";
import { api } from "../api.js";
import { renderUI, resetStore, screen, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";

const overview = {
    totals: { users: 2, transactions: 1234, accounts: 3, connections: 1 },
    newUsers30d: 1,
    activeUsers7d: 1,
    newUsers7d: 1,
    dbSizeBytes: 1536,
    registrations: [{ month: "2026-01", count: 1 }],
};
const user = {
    id: 7,
    email: "person@example.test",
    isAdmin: false,
    createdAt: "2026-01-01T12:00:00",
    lastLogin: "2026-02-03T12:30:00",
    accounts: 2,
    transactions: 12,
    lastTransaction: "2026-02-01",
    budgets: 3,
    connection: { status: "connected", lastSync: "2026-02-04", lastError: null },
};
const activity = {
    daily: [{ day: "2026-02-01", count: 4 }],
    features: [{ feature: "sync", count: 2 }],
    recentLogins: [{ email: user.email, at: "2026-02-03T12:30:00" }],
};
const detail = {
    user,
    accounts: [{ id: 1, name: "Card", transactions: 4, balance: 12345 }],
    featureUsage: [{ feature: "sync", count: 2 }],
    recentLogins: ["2026-02-03T12:30:00"],
    recentTransactions: [
        { id: 1, date: "2026-02-02", description: "Coffee", account: "Card", amount: -350 },
    ],
};

describe("AdminPage", () => {
    beforeEach(() => {
        resetStore();
        useStore.setState({ adminTick: 0, tabs: [] });
        vi.spyOn(api, "adminOverview").mockResolvedValue(overview);
        vi.spyOn(api, "adminUsers").mockResolvedValue([user]);
        vi.spyOn(api, "adminActivity").mockResolvedValue(activity);
    });
    afterEach(() => vi.restoreAllMocks());

    it("loads the dashboard, opens SQL and shows a user detail", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue(detail);
        const { user: events } = renderUI(<AdminPage />);
        await screen.findByRole("heading", { name: "Admin" });
        expect(screen.getByText("1.5 KB")).toBeInTheDocument();
        expect(screen.getAllByText("person@example.test")).toHaveLength(2);
        await events.click(screen.getByRole("button", { name: "SQL console" }));
        expect(useStore.getState().tabs).toEqual([expect.objectContaining({ kind: "admin-sql" })]);
        await events.click(screen.getAllByText("person@example.test")[1]);
        await screen.findByText("Recent transactions");
        expect(screen.getByText("Coffee")).toBeInTheDocument();
        await events.click(screen.getByRole("button", { name: "Manage" }));
        expect(useStore.getState().tabs).toEqual(
            expect.arrayContaining([expect.objectContaining({ kind: "admin-tx" })]),
        );
    });

    it("requires a second delete click and reloads the user table", async () => {
        vi.spyOn(api, "adminDeleteUser").mockResolvedValue({});
        const { user: events } = renderUI(<AdminPage />);
        await screen.findByRole("heading", { name: "Admin" });
        const remove = screen.getByRole("button", { name: "Delete" });
        await events.click(remove);
        expect(screen.getByRole("button", { name: "Sure?" })).toBeInTheDocument();
        expect(api.adminDeleteUser).not.toHaveBeenCalled();
        await events.click(screen.getByRole("button", { name: "Sure?" }));
        await waitFor(() => expect(api.adminDeleteUser).toHaveBeenCalledExactlyOnceWith(7));
        expect(api.adminOverview).toHaveBeenCalledTimes(2);
    });

    it("renders an API failure instead of an empty page", async () => {
        api.adminOverview.mockRejectedValueOnce(new Error("forbidden"));
        renderUI(<AdminPage />);
        expect(await screen.findByText("Failed to load admin data: forbidden")).toBeInTheDocument();
    });

    it("renders empty user data, admin and failed sync states", async () => {
        vi.spyOn(api, "adminUsers").mockResolvedValue([
            { ...user, id: 8, email: "admin@example.test", isAdmin: true, connection: null },
            {
                ...user,
                id: 9,
                email: "failed-sync@example.test",
                connection: { status: "error", lastSync: null, lastError: "token expired" },
            },
        ]);
        vi.spyOn(api, "adminActivity").mockResolvedValue({ ...activity, recentLogins: [] });
        vi.spyOn(api, "adminUserDetail").mockResolvedValue({
            user: { ...user, id: 8, email: "admin@example.test" },
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [],
        });
        const { user: events } = renderUI(<AdminPage />);
        await screen.findByText("No logins yet");
        expect(screen.getByText("admin")).toBeInTheDocument();
        expect(
            screen.getByText("failed-sync@example.test").closest("tr").querySelector(".admin-sync"),
        ).toHaveAttribute("title", "token expired");
        expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(1);

        await events.click(screen.getByText("admin@example.test"));
        expect(await screen.findByText("No accounts")).toBeInTheDocument();
        expect(screen.getByText("No API activity")).toBeInTheDocument();
        expect(screen.getByText("Never logged in")).toBeInTheDocument();
        expect(screen.getByText("No transactions")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Full" })).not.toBeInTheDocument();
    });

    it("downloads every transaction page from the detail", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue(detail);
        vi.spyOn(api, "adminUserTransactions")
            .mockResolvedValueOnce(Array.from({ length: 1000 }, (_, id) => ({ id })))
            .mockResolvedValueOnce([{ id: 1001 }]);
        const popup = { location: "", close: vi.fn() };
        vi.spyOn(window, "open").mockReturnValue(popup);
        vi.stubGlobal("URL", {
            createObjectURL: vi.fn(() => "blob:test"),
            revokeObjectURL: vi.fn(),
        });
        const { user: events } = renderUI(<AdminPage />);
        await screen.findByRole("heading", { name: "Admin" });
        await events.click(screen.getByRole("cell", { name: "person@example.test" }).closest("tr"));
        await events.click(await screen.findByRole("button", { name: "Full" }));
        await waitFor(() => expect(api.adminUserTransactions).toHaveBeenCalledTimes(2));
        expect(api.adminUserTransactions).toHaveBeenLastCalledWith(7, {
            limit: 1000,
            offset: 1000,
        });
        expect(popup.location).toBe("blob:test");
    });
});
