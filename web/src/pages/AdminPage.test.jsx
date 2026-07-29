import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@mantine/charts", () => ({
    AreaChart: () => <div data-testid="area-chart" />,
    BarChart: () => <div data-testid="bar-chart" />,
}));

import AdminPage from "./AdminPage.jsx";
import { api } from "../api.js";
import { fireEvent, renderUI, resetStore, screen, waitFor, within } from "../test/render.jsx";
import { useStore } from "../store.js";

// ru-RU grouping and the "₽" currency both use a non-breaking space (U+00A0)
const NBSP = "\u00a0";

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

    // the email also shows up in the recent-logins list, so the table row must
    // be located via its table cell rather than a bare text match
    const findUserRow = async (email = "person@example.test") =>
        (await screen.findByRole("cell", { name: email })).closest("tr");

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
        // the button starts idle (busy=false): not in Mantine's loading state
        expect(remove).not.toHaveAttribute("data-loading");
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
        // only the isAdmin user carries the "admin" badge; the other two do not
        expect(screen.getAllByText("admin")).toHaveLength(1);
        expect(
            screen.getByText("failed-sync@example.test").closest("tr").querySelector(".admin-sync"),
        ).toHaveAttribute("title", "token expired");
        expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(1);
        // the delete action sits on the non-admin row, and the admin row has none
        const adminRow = screen.getByText("admin@example.test").closest("tr");
        const nonAdminRow = screen.getByText("failed-sync@example.test").closest("tr");
        expect(within(adminRow).queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
        expect(within(nonAdminRow).getByRole("button", { name: "Delete" })).toBeInTheDocument();

        await events.click(screen.getByText("admin@example.test"));
        expect(await screen.findByText("No accounts")).toBeInTheDocument();
        expect(screen.getByText("No API activity")).toBeInTheDocument();
        expect(screen.getByText("Never logged in")).toBeInTheDocument();
        expect(screen.getByText("No transactions")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Full" })).not.toBeInTheDocument();
    });

    it("renders every KPI with its exact value and subtitle", async () => {
        const { container } = renderUI(<AdminPage />);
        await screen.findByRole("heading", { name: "Admin" });

        const kpis = within(container.querySelector(".admin-kpis"));
        const kpi = (label) => kpis.getByText(label).closest(".kpi");
        expect(within(kpi("Users")).getByText("2")).toBeInTheDocument();
        // the subtitle renders inside its own .kpi__sub element, not bare text
        expect(within(kpi("Users")).getByText("+1 in 30 days")).toHaveClass("kpi__sub");

        const active = kpi("Active users");
        expect(within(active).getByText("1")).toBeInTheDocument();
        expect(within(active).getByText("last 7 days")).toBeInTheDocument();
        expect(within(active).getByText("1")).toHaveStyle({ color: "var(--m-income)" });

        expect(within(kpi("New users")).getByText("last 7 days")).toBeInTheDocument();

        // transactions run through toLocaleString("ru-RU"): 1234 -> "1 234" (U+00A0)
        expect(kpi("Transactions").querySelector(".kpi__value").textContent).toBe(`1${NBSP}234`);
        expect(within(kpi("Transactions")).getByText("all users")).toBeInTheDocument();

        expect(within(kpi("Accounts")).getByText("3")).toBeInTheDocument();
        expect(within(kpi("Bank connections")).getByText("1")).toBeInTheDocument();
        // 1536 bytes -> 1.5 KB (v < 1024 false at B, /1024 = 1.5 < 100 -> toFixed(1))
        expect(within(kpi("Database")).getByText("1.5 KB")).toBeInTheDocument();
        expect(within(kpi("Database")).getByText("on disk")).toBeInTheDocument();
    });

    it("formats byte sizes across unit and rounding boundaries", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue(detail);
        const cases = [
            [null, "—"],
            [0, "0.0 B"],
            [1023, "1023 B"],
            [1024, "1.0 KB"],
            [100 * 1024, "100 KB"],
            [1536 * 1024, "1.5 MB"],
            [5 * 1024 ** 3, "5.0 GB"],
            [2048 * 1024 ** 3, "2048 GB"],
        ];
        for (const [bytes, want] of cases) {
            api.adminOverview.mockResolvedValue({ ...overview, dbSizeBytes: bytes });
            const { unmount } = renderUI(<AdminPage />);
            await screen.findByRole("heading", { name: "Admin" });
            expect(screen.getByText(want)).toBeInTheDocument();
            unmount();
        }
    });

    it("formats user-row dates, counts and sync badge exactly", async () => {
        renderUI(<AdminPage />);
        await screen.findByRole("heading", { name: "Admin" });
        const row = screen.getByRole("cell", { name: "person@example.test" }).closest("tr");

        // createdAt "2026-01-01T12:00:00" -> fmtDate slices to "2026-01-01"
        expect(within(row).getByText("2026-01-01")).toBeInTheDocument();
        // lastLogin -> fmtDt: first 16 chars, "T" -> " "
        expect(within(row).getByText("2026-02-03 12:30")).toBeInTheDocument();
        // lastTransaction already date-only
        expect(within(row).getByText("2026-02-01")).toBeInTheDocument();
        expect(within(row).getByText("2")).toBeInTheDocument();
        // transactions 12 through ru-RU locale (no grouping under 1000)
        expect(within(row).getByText("12")).toBeInTheDocument();
        expect(within(row).getByText("3")).toBeInTheDocument();

        const badge = row.querySelector(".admin-sync");
        expect(badge).toHaveTextContent("connected");
        // connected -> income tone dot; lastSync appended via fmtDate
        expect(badge.querySelector(".admin-sync__dot")).toHaveStyle({
            background: "var(--m-income)",
        });
        expect(badge).toHaveTextContent("· 2026-02-04");
        // no lastError -> no title attribute value
        expect(badge).not.toHaveAttribute("title");
    });

    it("shows an em dash for missing dates and no connection", async () => {
        vi.spyOn(api, "adminUsers").mockResolvedValue([
            {
                ...user,
                lastLogin: null,
                createdAt: null,
                lastTransaction: null,
                connection: null,
            },
        ]);
        renderUI(<AdminPage />);
        const row = await findUserRow();
        // three "—" from the three null dates, plus one from the muted no-connection badge
        expect(within(row).getAllByText("—")).toHaveLength(4);
        expect(row.querySelector(".admin-muted")).toHaveTextContent("—");
    });

    it("uses the warning tone for a pending sync without a last-sync date", async () => {
        vi.spyOn(api, "adminUsers").mockResolvedValue([
            {
                ...user,
                connection: { status: "pending", lastSync: null, lastError: null },
            },
        ]);
        renderUI(<AdminPage />);
        const badge = (await findUserRow()).querySelector(".admin-sync");
        expect(badge).toHaveTextContent("pending");
        expect(badge).not.toHaveTextContent("·");
        expect(badge.querySelector(".admin-sync__dot")).toHaveStyle({
            background: "var(--m-warning)",
        });
    });

    it("uses the expense tone for an errored sync", async () => {
        vi.spyOn(api, "adminUsers").mockResolvedValue([
            {
                ...user,
                connection: { status: "error", lastSync: "2026-02-04", lastError: "boom" },
            },
        ]);
        renderUI(<AdminPage />);
        const badge = (await findUserRow()).querySelector(".admin-sync");
        expect(badge.querySelector(".admin-sync__dot")).toHaveStyle({
            background: "var(--m-expense)",
        });
    });

    it("opens the admin-sql tab with the right key and kind", async () => {
        const { user: events } = renderUI(<AdminPage />);
        await events.click(await screen.findByRole("button", { name: "SQL console" }));
        expect(useStore.getState().tabs).toEqual([
            expect.objectContaining({ kind: "admin-sql", key: "admin-sql", props: {} }),
        ]);
    });

    it("toggles a user detail closed when the same row is clicked again", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue(detail);
        const { user: events } = renderUI(<AdminPage />);
        const row = await findUserRow();

        await events.click(row);
        await screen.findByText("Recent transactions");
        expect(api.adminUserDetail).toHaveBeenCalledExactlyOnceWith(7);

        await events.click(row);
        expect(screen.queryByText("Recent transactions")).not.toBeInTheDocument();
        // clicking the already-open row closes it without another fetch
        expect(api.adminUserDetail).toHaveBeenCalledTimes(1);
    });

    it("resets the delete arming when the pointer leaves the row", async () => {
        vi.spyOn(api, "adminDeleteUser").mockResolvedValue({});
        const { user: events } = renderUI(<AdminPage />);
        await screen.findByRole("heading", { name: "Admin" });
        const remove = screen.getByRole("button", { name: "Delete" });
        await events.click(remove);
        expect(screen.getByRole("button", { name: "Sure?" })).toBeInTheDocument();

        fireEvent.mouseLeave(remove.closest("tr"));
        expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Sure?" })).not.toBeInTheDocument();
        expect(api.adminDeleteUser).not.toHaveBeenCalled();
    });

    it("closes the user tab by key when a user is deleted", async () => {
        vi.spyOn(api, "adminDeleteUser").mockResolvedValue({});
        useStore.setState({
            tabs: [{ id: 1, key: "admin-tx:7", kind: "admin-tx", props: {} }],
        });
        const { user: events } = renderUI(<AdminPage />);
        await screen.findByRole("heading", { name: "Admin" });
        await events.click(screen.getByRole("button", { name: "Delete" }));
        await events.click(screen.getByRole("button", { name: "Sure?" }));
        await waitFor(() => expect(useStore.getState().tabs).toEqual([]));
    });

    it("refetches the dashboard and open detail when adminTick bumps", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue(detail);
        const { user: events } = renderUI(<AdminPage />);
        await events.click(await findUserRow());
        await screen.findByText("Recent transactions");
        expect(api.adminOverview).toHaveBeenCalledTimes(1);
        expect(api.adminUserDetail).toHaveBeenCalledTimes(1);

        await waitFor(() => useStore.getState().bumpAdminTick());
        await waitFor(() => expect(api.adminOverview).toHaveBeenCalledTimes(2));
        // the open detail is re-fetched for the same user id
        await waitFor(() => expect(api.adminUserDetail).toHaveBeenCalledTimes(2));
        expect(api.adminUserDetail).toHaveBeenLastCalledWith(7);
    });

    it("renders the detail lists, transaction preview and manage tab args", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue({
            user,
            accounts: [{ id: 1, name: "Card", transactions: 4, balance: 12345 }],
            featureUsage: [{ feature: "sync", count: 1234 }],
            recentLogins: Array.from({ length: 10 }, (_, i) => `2026-02-0${i % 9}T09:00:00`),
            recentTransactions: [
                {
                    id: 1,
                    date: "2026-02-02",
                    description: "",
                    category: "Food",
                    account: "Card",
                    amount: 500,
                },
                {
                    id: 2,
                    date: "2026-02-03",
                    description: "",
                    category: "",
                    account: "Cash",
                    amount: -75,
                },
                {
                    id: 3,
                    date: "2026-02-04",
                    description: "Zero",
                    category: "",
                    account: "Card",
                    amount: 0,
                },
            ],
        });
        const { user: events } = renderUI(<AdminPage />);
        await events.click(await findUserRow());
        const detailEl = (await screen.findByText("Recent transactions")).closest(".admin-detail");

        // populated lists must not render their empty-state rows
        expect(within(detailEl).queryByText("No accounts")).not.toBeInTheDocument();
        expect(within(detailEl).queryByText("No API activity")).not.toBeInTheDocument();
        expect(within(detailEl).queryByText("Never logged in")).not.toBeInTheDocument();
        expect(within(detailEl).queryByText("No transactions")).not.toBeInTheDocument();
        // account line: name · "4 tx", balance via money() -> "123 ₽" (12345 kop)
        expect(within(detailEl).getByText("· 4 tx")).toBeInTheDocument();
        expect(within(detailEl).getByText("123 ₽")).toBeInTheDocument();
        // feature count 1234 -> ru-RU "1 234"
        expect(within(detailEl).getByText("1 234")).toBeInTheDocument();
        // recent logins are capped at 8
        expect(
            detailEl.querySelectorAll(".admin-detail__col .admin-logins")[2].children,
        ).toHaveLength(8);

        // description empty -> falls back to category, then em dash
        expect(within(detailEl).getByText("Food")).toBeInTheDocument();
        expect(within(detailEl).getByText("—")).toBeInTheDocument();
        // positive amount gets the income colour, negative does not
        const pos = within(detailEl).getByText("5 ₽");
        expect(pos).toHaveStyle({ color: "var(--m-income)" });
        const neg = within(detailEl).getByText("-1 ₽");
        expect(neg.getAttribute("style") || "").not.toContain("var(--m-income)");
        // a zero amount is still >= 0, so it keeps the income colour (kills > 0)
        const zero = within(detailEl).getByText("0 ₽");
        expect(zero).toHaveStyle({ color: "var(--m-income)" });

        await events.click(within(detailEl).getByRole("button", { name: "Manage" }));
        expect(useStore.getState().tabs).toEqual([
            expect.objectContaining({
                kind: "admin-tx",
                key: "admin-tx:7",
                props: { user },
            }),
        ]);
    });

    it("caps the recent-transactions preview at five rows", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue({
            user,
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: Array.from({ length: 8 }, (_, i) => ({
                id: i,
                date: "2026-02-02",
                description: `tx ${i}`,
                account: "Card",
                amount: 100,
            })),
        });
        const { user: events } = renderUI(<AdminPage />);
        await events.click(await findUserRow());
        const table = (await screen.findByText("tx 0")).closest("table");
        expect(table.querySelectorAll("tbody tr")).toHaveLength(5);
        expect(screen.queryByText("tx 5")).not.toBeInTheDocument();
        expect(screen.getByText("tx 4")).toBeInTheDocument();
    });

    it("caps recent logins at twelve in the activity card", async () => {
        vi.spyOn(api, "adminActivity").mockResolvedValue({
            ...activity,
            recentLogins: Array.from({ length: 15 }, (_, i) => ({
                email: `u${i}@example.test`,
                at: "2026-02-03T12:30:00",
            })),
        });
        renderUI(<AdminPage />);
        const list = (await screen.findByText("Recent logins"))
            .closest(".chart-card")
            .querySelector(".admin-logins");
        expect(list.children).toHaveLength(12);
        expect(screen.getByText("u11@example.test")).toBeInTheDocument();
        expect(screen.queryByText("u12@example.test")).not.toBeInTheDocument();
        // a non-empty list must not print the empty-state row
        expect(screen.queryByText("No logins yet")).not.toBeInTheDocument();
    });

    it("surfaces a toast when loading a user detail fails", async () => {
        vi.spyOn(api, "adminUserDetail").mockRejectedValue(new Error("nope"));
        const { user: events } = renderUI(<AdminPage />);
        await events.click(await findUserRow());
        expect(await screen.findByText("Failed to load user")).toBeInTheDocument();
        expect(screen.getByText("nope")).toBeInTheDocument();
    });

    it("stops before opening a popup when the detail has no recent transactions", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue({
            user,
            accounts: [],
            featureUsage: [],
            recentLogins: [],
            recentTransactions: [],
        });
        const { user: events } = renderUI(<AdminPage />);
        await events.click(await findUserRow());
        await screen.findByText("No transactions");
        expect(screen.queryByRole("button", { name: "Full" })).not.toBeInTheDocument();
        expect(screen.getByText("No accounts")).toBeInTheDocument();
    });

    it("stops paging once a short transaction page comes back", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue(detail);
        vi.spyOn(api, "adminUserTransactions").mockResolvedValueOnce([{ id: 1 }, { id: 2 }]);
        const popup = { location: "", close: vi.fn() };
        vi.spyOn(window, "open").mockReturnValue(popup);
        vi.stubGlobal("URL", {
            createObjectURL: vi.fn(() => "blob:short"),
            revokeObjectURL: vi.fn(),
        });
        const { user: events } = renderUI(<AdminPage />);
        await events.click(await findUserRow());
        await events.click(await screen.findByRole("button", { name: "Full" }));
        await waitFor(() => expect(popup.location).toBe("blob:short"));
        // first page (2 < 1000) ends the loop immediately
        expect(api.adminUserTransactions).toHaveBeenCalledExactlyOnceWith(7, {
            limit: 1000,
            offset: 0,
        });
    });

    it("closes the popup and toasts when the full export fails", async () => {
        vi.spyOn(api, "adminUserDetail").mockResolvedValue(detail);
        vi.spyOn(api, "adminUserTransactions").mockRejectedValue(new Error("export boom"));
        const popup = { location: "", close: vi.fn() };
        vi.spyOn(window, "open").mockReturnValue(popup);
        const { user: events } = renderUI(<AdminPage />);
        await events.click(await findUserRow());
        await events.click(await screen.findByRole("button", { name: "Full" }));
        await waitFor(() => expect(popup.close).toHaveBeenCalledTimes(1));
        expect(await screen.findByText("Failed to load transactions")).toBeInTheDocument();
        expect(screen.getByText("export boom")).toBeInTheDocument();
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
