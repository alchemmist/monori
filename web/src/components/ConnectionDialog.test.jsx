import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import ConnectionDialog from "./ConnectionDialog.jsx";

const account = { id: 1, name: "Card", bankRef: "old-ref" };
const connector = {
    bank: "demo",
    kind: "web",
    label: "Demo Bank",
    connectionParams: [{ name: "login", label: "Login", required: true }],
    accountParams: [{ name: "account", label: "Bank account", help: "IBAN", required: true }],
};

describe("ConnectionDialog", () => {
    beforeEach(() => {
        resetStore();
        seed({ accounts: [account] });
        vi.clearAllMocks();
    });

    it("creates a login, links the account and enters the SMS confirmation step", async () => {
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        const create = vi
            .spyOn(useStore.getState(), "createConnection")
            .mockResolvedValue({ id: 7 });
        const patch = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        vi.spyOn(useStore.getState(), "syncConnection").mockResolvedValue({
            status: "awaiting_sms",
        });
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        expect(await screen.findByText(/Connects to Demo Bank/)).toBeInTheDocument();
        const connect = screen.getByRole("button", { name: "Connect & sync" });
        expect(connect).toBeDisabled();
        await user.type(screen.getByLabelText("Login"), "alice");
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "40817");
        await user.click(connect);
        await waitFor(() =>
            expect(create).toHaveBeenCalledWith({
                bank: "demo",
                kind: "web",
                credentials: { login: "alice" },
            }),
        );
        expect(patch).toHaveBeenCalledWith(1, { connectionId: 7, bankRef: "40817" });
        expect(await screen.findByLabelText("SMS code")).toBeInTheDocument();
    });

    it("submits an SMS code and displays sync results", async () => {
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        vi.spyOn(useStore.getState(), "createConnection").mockResolvedValue({ id: 7 });
        vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        vi.spyOn(useStore.getState(), "syncConnection").mockResolvedValue({
            status: "awaiting_sms",
        });
        const sms = vi.spyOn(useStore.getState(), "submitConnectionSms").mockResolvedValue({
            status: "connected",
            inserted: 3,
            skipped: 1,
            dateFrom: "2026-07-01",
            dateTo: "2026-07-02",
        });
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await waitFor(() => expect(api.connectionsAvailable).toHaveBeenCalled());
        await user.type(screen.getByLabelText("Login"), "alice");
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "40817");
        await user.click(screen.getByRole("button", { name: "Connect & sync" }));
        await user.type(await screen.findByLabelText("SMS code"), "1234");
        await user.click(screen.getByRole("button", { name: "Confirm" }));
        await waitFor(() => expect(sms).toHaveBeenCalledWith(7, "1234"));
        expect(await screen.findByText(/3 new, 1 duplicates skipped/)).toBeInTheDocument();
    });

    it("saves a changed bank reference and unlinks an existing connection", async () => {
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        const patch = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        const close = vi.fn();
        const { user } = renderUI(
            <ConnectionDialog
                account={account}
                connection={{
                    id: 9,
                    bank: "demo",
                    kind: "web",
                    status: "connected",
                    lastSync: null,
                }}
                onClose={close}
            />,
        );
        await screen.findByText("connected");
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "new-ref");
        await user.click(screen.getByRole("button", { name: "Save bank account" }));
        await waitFor(() => expect(patch).toHaveBeenCalledWith(1, { bankRef: "new-ref" }));
        await user.click(screen.getByRole("button", { name: "Unlink account" }));
        await waitFor(() => expect(patch).toHaveBeenCalledWith(1, { connectionId: 0 }));
        expect(close).toHaveBeenCalled();
    });

    it("reuses an existing login and shows the full sync outcome", async () => {
        seed({
            accounts: [account],
            connections: [{ id: 12, bank: "demo", kind: "web" }],
        });
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        const create = vi.spyOn(useStore.getState(), "createConnection");
        const patch = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        vi.spyOn(useStore.getState(), "syncConnection").mockResolvedValue({
            status: "connected",
            inserted: 2,
            skipped: 3,
            accounts: [1, 2],
            unmappedTails: [{ tail: "9999", rows: 2 }],
        });
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await screen.findByText(/Connects to Demo Bank/);
        await user.click(screen.getByRole("button", { name: /Bank login/ }));
        await user.click(await screen.findByText("Demo Bank login #12"));
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "new-ref");
        await user.click(screen.getByRole("button", { name: "Connect & sync" }));
        await screen.findByText(/2 new, 3 duplicates skipped across 2 accounts/);
        expect(create).not.toHaveBeenCalled();
        expect(patch).toHaveBeenCalledWith(1, { connectionId: 12, bankRef: "new-ref" });
        expect(screen.getByText(/Cards not bound to any account: \*9999/)).toBeInTheDocument();
    });

    it("only offers logins made with the very same connector", async () => {
        seed({
            accounts: [account],
            connections: [
                { id: 12, bank: "demo", kind: "web" },
                { id: 13, bank: "demo", kind: "api" },
                { id: 14, bank: "other", kind: "web" },
            ],
        });
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await screen.findByText(/Connects to Demo Bank/);
        await user.click(screen.getByRole("button", { name: /Bank login/ }));
        const offered = (await screen.findAllByRole("option")).map((o) => o.textContent);
        expect(offered).toEqual(["New login…", "Demo Bank login #12"]);
    });

    it("makes the user pick a bank when several connectors are available", async () => {
        const other = { ...connector, bank: "other", kind: "web", label: "Other Bank" };
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector, other]);
        renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await waitFor(() => expect(api.connectionsAvailable).toHaveBeenCalled());
        // nothing preselected: no connector blurb, no credential fields, nothing to submit
        expect(screen.queryByText(/Connects to/)).not.toBeInTheDocument();
        expect(screen.queryByLabelText("Login")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Connect & sync" })).toBeDisabled();
        expect(screen.getByText("Pick a bank")).toBeInTheDocument();
    });

    it("keeps OTP open after rejection, cancels it on close, and retries sync errors", async () => {
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        vi.spyOn(useStore.getState(), "createConnection").mockResolvedValue({ id: 7 });
        vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        const sync = vi
            .spyOn(useStore.getState(), "syncConnection")
            .mockResolvedValueOnce({ status: "awaiting_sms" })
            .mockRejectedValueOnce(new Error("network"));
        const sms = vi
            .spyOn(useStore.getState(), "submitConnectionSms")
            .mockResolvedValueOnce({ status: "awaiting_sms", message: "Wrong code" });
        const cancel = vi.spyOn(useStore.getState(), "cancelConnectionSync").mockResolvedValue();
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await screen.findByLabelText("Login");
        await user.type(screen.getByLabelText("Login"), "alice");
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "ref");
        await user.click(screen.getByRole("button", { name: "Connect & sync" }));
        await user.type(await screen.findByLabelText("SMS code"), "bad");
        await user.click(screen.getByRole("button", { name: "Confirm" }));
        expect(await screen.findByText("Wrong code")).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Cancel" }));
        await waitFor(() => expect(cancel).toHaveBeenCalledWith(7));

        const ready = renderUI(
            <ConnectionDialog
                account={account}
                connection={{ id: 9, bank: "demo", kind: "web", status: "error", lastSync: null }}
                onClose={vi.fn()}
            />,
        );
        await screen.findByText("error");
        await ready.user.click(screen.getByRole("button", { name: "Sync now" }));
        expect(await screen.findByText("Error: network")).toBeInTheDocument();
        await ready.user.click(screen.getByRole("button", { name: "Retry" }));
        await waitFor(() => expect(sync).toHaveBeenCalledWith(9));
    });

    it("reports loading, saving, unlinking, and disconnecting failures", async () => {
        const notify = vi.spyOn(useStore.getState(), "notify");
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        const patch = vi
            .spyOn(useStore.getState(), "patchAccount")
            .mockRejectedValue(new Error("offline"));
        vi.spyOn(useStore.getState(), "deleteConnection").mockRejectedValue(new Error("offline"));
        const { user } = renderUI(
            <ConnectionDialog
                account={account}
                connection={{
                    id: 9,
                    bank: "demo",
                    kind: "web",
                    status: "disconnected",
                    lastSync: null,
                }}
                onClose={vi.fn()}
            />,
        );
        await screen.findByText("disconnected");
        await screen.findByLabelText("Bank account");
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "changed");
        await user.click(screen.getByRole("button", { name: "Save bank account" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Failed to save bank account" }),
            ),
        );
        await user.click(screen.getByRole("button", { name: "Unlink account" }));
        await user.click(screen.getByRole("button", { name: "Disconnect bank" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Failed to disconnect" }),
            ),
        );
        expect(patch).toHaveBeenCalledWith(1, { connectionId: 0 });
    });

    it("notifies when the bank list cannot be loaded", async () => {
        const notify = vi.spyOn(useStore.getState(), "notify");
        vi.spyOn(api, "connectionsAvailable").mockRejectedValue(new Error("unavailable"));
        renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Failed to load banks" }),
            ),
        );
    });
});
