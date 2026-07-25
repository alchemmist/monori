import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import ConnectionDialog from "./ConnectionDialog.jsx";

const account = { id: 1, name: "Card", bankRef: "old-ref" };
const connector = {
    bank: "demo", kind: "web", label: "Demo Bank",
    connectionParams: [{ name: "login", label: "Login", required: true }],
    accountParams: [{ name: "account", label: "Bank account", help: "IBAN", required: true }],
};

describe("ConnectionDialog", () => {
    beforeEach(() => { resetStore(); seed({ accounts: [account] }); vi.clearAllMocks(); });

    it("creates a login, links the account and enters the SMS confirmation step", async () => {
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        const create = vi.spyOn(useStore.getState(), "createConnection").mockResolvedValue({ id: 7 });
        const patch = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        vi.spyOn(useStore.getState(), "syncConnection").mockResolvedValue({ status: "awaiting_sms" });
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        expect(await screen.findByText(/Connects to Demo Bank/)).toBeInTheDocument();
        const connect = screen.getByRole("button", { name: "Connect & sync" });
        expect(connect).toBeDisabled();
        await user.type(screen.getByLabelText("Login"), "alice");
        await user.clear(screen.getByLabelText("Bank account")); await user.type(screen.getByLabelText("Bank account"), "40817");
        await user.click(connect);
        await waitFor(() => expect(create).toHaveBeenCalledWith({ bank: "demo", kind: "web", credentials: { login: "alice" } }));
        expect(patch).toHaveBeenCalledWith(1, { connectionId: 7, bankRef: "40817" });
        expect(await screen.findByLabelText("SMS code")).toBeInTheDocument();
    });

    it("submits an SMS code and displays sync results", async () => {
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        vi.spyOn(useStore.getState(), "createConnection").mockResolvedValue({ id: 7 });
        vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        vi.spyOn(useStore.getState(), "syncConnection").mockResolvedValue({ status: "awaiting_sms" });
        const sms = vi.spyOn(useStore.getState(), "submitConnectionSms").mockResolvedValue({ status: "connected", inserted: 3, skipped: 1, dateFrom: "2026-07-01", dateTo: "2026-07-02" });
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await waitFor(() => expect(api.connectionsAvailable).toHaveBeenCalled());
        await user.type(screen.getByLabelText("Login"), "alice");
        await user.clear(screen.getByLabelText("Bank account")); await user.type(screen.getByLabelText("Bank account"), "40817");
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
        const { user } = renderUI(<ConnectionDialog account={account} connection={{ id: 9, bank: "demo", kind: "web", status: "connected", lastSync: null }} onClose={close} />);
        await screen.findByText("connected");
        await user.clear(screen.getByLabelText("Bank account")); await user.type(screen.getByLabelText("Bank account"), "new-ref");
        await user.click(screen.getByRole("button", { name: "Save bank account" }));
        await waitFor(() => expect(patch).toHaveBeenCalledWith(1, { bankRef: "new-ref" }));
        await user.click(screen.getByRole("button", { name: "Unlink account" }));
        await waitFor(() => expect(patch).toHaveBeenCalledWith(1, { connectionId: 0 }));
        expect(close).toHaveBeenCalled();
    });
});
