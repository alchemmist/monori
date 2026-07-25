import { describe, it, expect, beforeEach, vi } from "vitest";
import TabHost from "./TabHost.jsx";
import { renderUI, screen, waitFor, resetStore, seed } from "../test/render.jsx";
import { useStore } from "../store.js";

// each stub reports the props it was handed and exposes its close callback
vi.mock("./AccountDialogs.jsx", () => ({
    AccountEditTab: (props) => (
        <div data-testid="account-edit" data-account={props.account?.name ?? ""}>
            <button onClick={props.onClose}>close account-edit</button>
        </div>
    ),
}));

vi.mock("./AdminSqlTab.jsx", () => ({
    default: (props) => (
        <div data-testid="admin-sql">
            <button onClick={props.onClose}>close admin-sql</button>
        </div>
    ),
}));

vi.mock("./AdminTxTab.jsx", () => ({
    default: (props) => (
        <div data-testid="admin-tx" data-user={props.user?.email ?? ""}>
            <button onClick={props.onClose}>close admin-tx</button>
        </div>
    ),
}));

vi.mock("./MigratePanel.jsx", () => ({
    default: (props) => (
        <div data-testid="migrate">
            <button onClick={props.onClose}>close migrate</button>
        </div>
    ),
}));

const openTabs = (...tabs) => useStore.setState({ tabs });

describe("TabHost", () => {
    beforeEach(() => {
        resetStore();
        seed();
    });

    it("hands the account row of the open tab to the account editor", () => {
        openTabs({ id: 1, kind: "account-edit", props: { accountId: 1 }, key: null });
        renderUI(<TabHost />);
        expect(screen.getByTestId("account-edit")).toHaveAttribute("data-account", "Card");
    });

    it("closes the account tab when its account disappears from the snapshot", async () => {
        openTabs({ id: 1, kind: "account-edit", props: { accountId: 1 }, key: null });
        renderUI(<TabHost />);
        expect(screen.getByTestId("account-edit")).toBeInTheDocument();

        seed({ accounts: [] });
        await waitFor(() => expect(screen.queryByTestId("account-edit")).not.toBeInTheDocument());
        expect(useStore.getState().tabs).toHaveLength(0);
    });

    it("passes the subject user to the admin transactions tab", () => {
        const user = { id: 7, email: "person@example.test" };
        openTabs({ id: 1, kind: "admin-tx", props: { user }, key: null });
        renderUI(<TabHost />);
        expect(screen.getByTestId("admin-tx")).toHaveAttribute("data-user", "person@example.test");
    });

    it("renders every open tab side by side and closes only the one asked for", async () => {
        openTabs(
            { id: 1, kind: "admin-tx", props: { user: { id: 7, email: "a@b.test" } }, key: null },
            { id: 2, kind: "admin-sql", props: {}, key: null },
            { id: 3, kind: "migrate", props: {}, key: null },
        );
        const { user } = renderUI(<TabHost />);
        expect(screen.getByTestId("admin-tx")).toBeInTheDocument();
        expect(screen.getByTestId("admin-sql")).toBeInTheDocument();
        expect(screen.getByTestId("migrate")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "close admin-sql" }));
        await waitFor(() => expect(screen.queryByTestId("admin-sql")).not.toBeInTheDocument());
        expect(useStore.getState().tabs.map((t) => t.id)).toEqual([1, 3]);
        expect(screen.getByTestId("admin-tx")).toBeInTheDocument();
        expect(screen.getByTestId("migrate")).toBeInTheDocument();
    });

    it("drops a restored tab whose kind this build no longer knows", async () => {
        openTabs({ id: 1, kind: "unknown", props: {}, key: null });
        renderUI(<TabHost />);
        await waitFor(() => expect(useStore.getState().tabs).toHaveLength(0));
    });
});
