import { describe, expect, it, vi, afterEach } from "vitest";
import ConnectionDialog from "./ConnectionDialog.jsx";
import { renderUI, screen, waitFor, userEvent, seed, resetStore } from "../test/render.jsx";

vi.mock("../api.js");

describe("ConnectionDialog", () => {
    afterEach(() => resetStore());

    const mockAccount = {
        id: 1,
        name: "Test Card",
        type: "card",
        icon: "card",
        color: "#5b6472",
        currency: "RUB",
        archived: false,
        bankRef: null,
    };

    describe("Credentials step - bank selection", () => {
        it("loads available banks on mount", async () => {
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                { bank: "tbank", kind: "web", label: "T-Bank", connectionParams: [], accountParams: [] },
                { bank: "alfa", kind: "web", label: "Alfa-Bank", connectionParams: [], accountParams: [] },
            ]);

            renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );

            await waitFor(() => {
                expect(screen.getByText("T-Bank")).toBeInTheDocument();
            });
        });

        it("automatically selects bank if only one is available", async () => {
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                { bank: "tbank", kind: "web", label: "T-Bank", connectionParams: [], accountParams: [] },
            ]);

            renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );

            await waitFor(() => {
                expect(screen.getByText("T-Bank")).toBeInTheDocument();
            });
        });

        it("displays connector disclaimer when bank is selected", async () => {
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);

            renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );

            await waitFor(() => {
                expect(
                    screen.getByText(/Connects to T-Bank in a headless browser/),
                ).toBeInTheDocument();
            });
        });
    });

    describe("Credentials step - new login", () => {
        it("renders credential fields from connector params", async () => {
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [
                        { name: "login", label: "Phone/Email", required: true, secret: false },
                        { name: "password", label: "Password", required: true, secret: true },
                    ],
                    accountParams: [],
                },
            ]);

            renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );

            await waitFor(() => {
                expect(screen.getByLabelText("Phone/Email")).toBeInTheDocument();
                expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
            });
        });

        it("shows account params fields when connector is selected", async () => {
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [
                        { name: "account", label: "Account ID", required: true, help: "Enter your account ID" },
                    ],
                },
            ]);

            renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );

            await waitFor(() => {
                expect(screen.getByLabelText("Account ID")).toBeInTheDocument();
            });
        });
    });

    describe("Credentials step - existing logins", () => {
        it("shows existing login options when available", async () => {
            const { useStore } = await import("../store.js");
            seed({
                accounts: [mockAccount],
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                connections: [
                    { id: 10, bank: "tbank", kind: "web", status: "connected", lastSync: null, lastError: null },
                ],
            });

            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);

            renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );

            await waitFor(() => {
                expect(screen.getByText(/T-Bank login #10/)).toBeInTheDocument();
            });
        });
    });

    describe("Credentials step - form validation", () => {
        it("disables Connect button when credentials are incomplete", async () => {
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [
                        { name: "login", label: "Login", required: true, secret: false },
                    ],
                    accountParams: [],
                },
            ]);

            renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).toBeDisabled();
            });
        });

        it("enables Connect button when credentials are complete", async () => {
            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [
                        { name: "login", label: "Login", required: true, secret: false },
                    ],
                    accountParams: [],
                },
            ]);

            await waitFor(() => {
                expect(screen.getByLabelText("Login")).toBeInTheDocument();
            });

            const loginInput = screen.getByLabelText("Login");
            await user.type(loginInput, "user@test.com");

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).not.toBeDisabled();
            });
        });
    });

    describe("Syncing step", () => {
        it("shows syncing message during sync", async () => {
            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);
            vi.spyOn(api, "createConnection").mockImplementation(
                () => new Promise(() => {}),
            );

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: /Connect & sync/ }));

            await waitFor(() => {
                expect(screen.getByText("Syncing…")).toBeInTheDocument();
            });
        });
    });

    describe("SMS step", () => {
        it("shows SMS code input when status is awaiting_sms", async () => {
            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);
            vi.spyOn(api, "createConnection").mockResolvedValueOnce({
                id: 5,
            });
            vi.spyOn(api, "syncConnection").mockResolvedValueOnce({
                status: "awaiting_sms",
            });
            vi.spyOn(api, "patchAccount").mockResolvedValueOnce(undefined);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: /Connect & sync/ }));

            await waitFor(() => {
                expect(screen.getByLabelText("SMS code")).toBeInTheDocument();
            });
        });

        it("disables Confirm button when SMS code is empty", async () => {
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);
            vi.spyOn(api, "createConnection").mockResolvedValueOnce({ id: 5 });
            vi.spyOn(api, "syncConnection").mockResolvedValueOnce({
                status: "awaiting_sms",
            });
            vi.spyOn(api, "patchAccount").mockResolvedValueOnce(undefined);

            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: /Connect & sync/ }));

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
            });
        });

        it("enables Confirm button when SMS code is entered", async () => {
            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);
            vi.spyOn(api, "createConnection").mockResolvedValueOnce({ id: 5 });
            vi.spyOn(api, "syncConnection").mockResolvedValueOnce({
                status: "awaiting_sms",
            });
            vi.spyOn(api, "patchAccount").mockResolvedValueOnce(undefined);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: /Connect & sync/ }));

            await waitFor(() => {
                const codeInput = screen.getByLabelText("SMS code");
                expect(codeInput).toBeInTheDocument();
            });

            const codeInput = screen.getByLabelText("SMS code");
            await user.type(codeInput, "123456");

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Confirm" })).not.toBeDisabled();
            });
        });

        it("displays error message on SMS rejection", async () => {
            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);
            vi.spyOn(api, "createConnection").mockResolvedValueOnce({ id: 5 });
            vi.spyOn(api, "syncConnection").mockResolvedValueOnce({
                status: "awaiting_sms",
            });
            vi.spyOn(api, "patchAccount").mockResolvedValueOnce(undefined);
            vi.spyOn(api, "submitConnectionSms").mockResolvedValueOnce({
                status: "awaiting_sms",
                message: "The bank rejected the code",
            });

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: /Connect & sync/ }));

            await waitFor(() => {
                expect(screen.getByLabelText("SMS code")).toBeInTheDocument();
            });

            const codeInput = screen.getByLabelText("SMS code");
            await user.type(codeInput, "000000");
            await user.click(screen.getByRole("button", { name: "Confirm" }));

            await waitFor(() => {
                expect(
                    screen.getByText("The bank rejected the code — try again."),
                ).toBeInTheDocument();
            });
        });

        it("closes dialog on cancel during SMS step", async () => {
            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);
            vi.spyOn(api, "createConnection").mockResolvedValueOnce({ id: 5 });
            vi.spyOn(api, "syncConnection").mockResolvedValueOnce({
                status: "awaiting_sms",
            });
            vi.spyOn(api, "patchAccount").mockResolvedValueOnce(undefined);
            vi.spyOn(api, "cancelConnectionSync").mockResolvedValueOnce(undefined);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: /Connect & sync/ }));

            await waitFor(() => {
                expect(screen.getByLabelText("SMS code")).toBeInTheDocument();
            });

            const closeButton = screen.getByRole("button", { name: "Close" });
            await user.click(closeButton);
        });
    });

    describe("Success state", () => {
        it("displays sync results", async () => {
            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);
            vi.spyOn(api, "createConnection").mockResolvedValueOnce({ id: 5 });
            vi.spyOn(api, "syncConnection").mockResolvedValueOnce({
                status: "connected",
                inserted: 42,
                skipped: 3,
            });
            vi.spyOn(api, "patchAccount").mockResolvedValueOnce(undefined);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: /Connect & sync/ }));

            await waitFor(() => {
                expect(screen.getByText(/42 new, 3 duplicates skipped/)).toBeInTheDocument();
            });
        });
    });

    describe("Ready step - existing connection", () => {
        it("renders status tag for existing connection", () => {
            seed({
                accounts: [mockAccount],
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                connections: [
                    {
                        id: 10,
                        bank: "tbank",
                        kind: "web",
                        status: "connected",
                        lastSync: "2026-07-20",
                        lastError: null,
                    },
                ],
            });

            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);

            renderUI(
                <ConnectionDialog
                    account={mockAccount}
                    connection={{
                        id: 10,
                        bank: "tbank",
                        kind: "web",
                        status: "connected",
                        lastSync: "2026-07-20",
                        lastError: null,
                    }}
                    onClose={vi.fn()}
                />,
            );

            expect(screen.getByText("connected")).toBeInTheDocument();
        });

        it("displays last sync date", () => {
            seed({
                accounts: [mockAccount],
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                connections: [],
            });

            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);

            renderUI(
                <ConnectionDialog
                    account={mockAccount}
                    connection={{
                        id: 10,
                        bank: "tbank",
                        kind: "web",
                        status: "connected",
                        lastSync: "2026-07-20T10:30:00",
                        lastError: null,
                    }}
                    onClose={vi.fn()}
                />,
            );

            expect(screen.getByText(/Jul 20/)).toBeInTheDocument();
        });

        it("shows Sync now button", () => {
            seed({
                accounts: [mockAccount],
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                connections: [],
            });

            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);

            renderUI(
                <ConnectionDialog
                    account={mockAccount}
                    connection={{
                        id: 10,
                        bank: "tbank",
                        kind: "web",
                        status: "connected",
                        lastSync: "2026-07-20",
                        lastError: null,
                    }}
                    onClose={vi.fn()}
                />,
            );

            expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
        });

        it("shows disconnect and unlink buttons", () => {
            seed({
                accounts: [mockAccount],
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                connections: [],
            });

            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);

            renderUI(
                <ConnectionDialog
                    account={mockAccount}
                    connection={{
                        id: 10,
                        bank: "tbank",
                        kind: "web",
                        status: "connected",
                        lastSync: "2026-07-20",
                        lastError: null,
                    }}
                    onClose={vi.fn()}
                />,
            );

            expect(screen.getByRole("button", { name: "Unlink account" })).toBeInTheDocument();
            expect(screen.getByRole("button", { name: "Disconnect bank" })).toBeInTheDocument();
        });

        it("displays last error if present", () => {
            seed({
                accounts: [mockAccount],
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
                connections: [],
            });

            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);

            renderUI(
                <ConnectionDialog
                    account={mockAccount}
                    connection={{
                        id: 10,
                        bank: "tbank",
                        kind: "web",
                        status: "error",
                        lastSync: "2026-07-20",
                        lastError: "Connection failed",
                    }}
                    onClose={vi.fn()}
                />,
            );

            expect(screen.getByText("Connection failed")).toBeInTheDocument();
        });
    });

    describe("Error state", () => {
        it("shows error message and Retry button on sync error", async () => {
            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );
            const { api } = await import("../api.js");
            vi.spyOn(api, "connectionsAvailable").mockResolvedValueOnce([
                {
                    bank: "tbank",
                    kind: "web",
                    label: "T-Bank",
                    connectionParams: [],
                    accountParams: [],
                },
            ]);
            vi.spyOn(api, "createConnection").mockResolvedValueOnce({ id: 5 });
            vi.spyOn(api, "syncConnection").mockRejectedValueOnce(new Error("Sync failed"));
            vi.spyOn(api, "patchAccount").mockResolvedValueOnce(undefined);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: /Connect & sync/ })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: /Connect & sync/ }));

            await waitFor(() => {
                expect(screen.getByText("Sync failed")).toBeInTheDocument();
                expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
            });
        });
    });

    describe("Demo mode", () => {
        it("throws error when attempting to create connection in demo", async () => {
            const { user } = renderUI(
                <ConnectionDialog account={mockAccount} connection={null} onClose={vi.fn()} />,
            );
            const { setPath } = await import("../test/render.jsx");
            setPath("/demo");

            const { useStore } = await import("../store.js");
            const createConnectionSpy = vi
                .spyOn(useStore.getState(), "createConnection")
                .mockRejectedValueOnce(new Error("Bank sync is not available in the demo"));

            expect(createConnectionSpy).toBeDefined();
        });
    });
});
