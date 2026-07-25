import { describe, it, expect, beforeEach, vi } from "vitest";
import TabHost from "./TabHost.jsx";
import { renderUI, screen, waitFor, resetStore } from "../test/render.jsx";
import { useStore } from "../store.js";

vi.mock("./AccountDialogs.jsx", () => ({
    AccountEditTab: ({ onClose }) => <div data-testid="account-edit">AccountEditTab</div>,
}));

vi.mock("./AdminSqlTab.jsx", () => ({
    default: ({ onClose }) => <div data-testid="admin-sql">AdminSqlTab</div>,
}));

vi.mock("./AdminTxTab.jsx", () => ({
    default: ({ onClose }) => <div data-testid="admin-tx">AdminTxTab</div>,
}));

vi.mock("./MigratePanel.jsx", () => ({
    default: ({ onClose }) => <div data-testid="migrate">MigratePanel</div>,
}));

describe("TabHost", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders tabs from store when open", () => {
        useStore.setState({
            tabs: [{ id: 1, kind: "account-edit", props: { accountId: 1 }, key: null }],
            snapshot: {
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
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                connections: [],
            },
            loading: false,
            error: null,
        });
        renderUI(<TabHost />);
        expect(screen.getByTestId("account-edit")).toBeTruthy();
    });

    it("closes account tab when account is deleted", async () => {
        useStore.setState({
            tabs: [{ id: 1, kind: "account-edit", props: { accountId: 1 }, key: null }],
            snapshot: {
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
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                connections: [],
            },
            loading: false,
            error: null,
        });
        renderUI(<TabHost />);
        expect(screen.getByTestId("account-edit")).toBeTruthy();
        useStore.setState({
            snapshot: {
                accounts: [],
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                connections: [],
            },
        });
        await waitFor(() => {
            expect(screen.queryByTestId("account-edit")).toBeFalsy();
        });
    });

    it("renders admin-tx tab", () => {
        useStore.setState({
            tabs: [{ id: 1, kind: "admin-tx", props: { user: { id: 1 } }, key: null }],
        });
        renderUI(<TabHost />);
        expect(screen.getByTestId("admin-tx")).toBeTruthy();
    });

    it("renders admin-sql tab", () => {
        useStore.setState({
            tabs: [{ id: 1, kind: "admin-sql", props: {}, key: null }],
        });
        renderUI(<TabHost />);
        expect(screen.getByTestId("admin-sql")).toBeTruthy();
    });

    it("renders migrate tab", () => {
        useStore.setState({
            tabs: [{ id: 1, kind: "migrate", props: {}, key: null }],
        });
        renderUI(<TabHost />);
        expect(screen.getByTestId("migrate")).toBeTruthy();
    });

    it("closes unknown tab automatically", async () => {
        useStore.setState({
            tabs: [{ id: 1, kind: "unknown", props: {}, key: null }],
        });
        renderUI(<TabHost />);
        await waitFor(() => {
            expect(useStore.getState().tabs).toHaveLength(0);
        });
    });

    it("renders multiple different tabs", () => {
        useStore.setState({
            tabs: [
                { id: 1, kind: "admin-tx", props: { user: { id: 1 } }, key: null },
                { id: 2, kind: "admin-sql", props: {}, key: null },
            ],
        });
        renderUI(<TabHost />);
        expect(screen.getByTestId("admin-tx")).toBeTruthy();
        expect(screen.getByTestId("admin-sql")).toBeTruthy();
    });
});
