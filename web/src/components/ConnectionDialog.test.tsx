import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent } from "@testing-library/react";
import { api } from "../api.js";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import type { SyncResult } from "../types.js";
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
        let finishSync: (result: SyncResult) => void = () => undefined;
        const pendingSync = new Promise<SyncResult>((resolve) => {
            finishSync = resolve;
        });
        const sms = vi
            .spyOn(useStore.getState(), "submitConnectionSms")
            .mockReturnValue(pendingSync);
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await waitFor(() => expect(api.connectionsAvailable).toHaveBeenCalled());
        await user.type(screen.getByLabelText("Login"), "alice");
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "40817");
        await user.click(screen.getByRole("button", { name: "Connect & sync" }));
        const input = await screen.findByLabelText("SMS code");
        expect(input).not.toHaveAttribute("inputmode");
        expect(input).not.toHaveAttribute("maxlength");
        expect(input).not.toHaveAttribute("placeholder");
        expect(screen.queryByRole("button", { name: /Resend SMS/ })).not.toBeInTheDocument();
        const confirm = screen.getByRole("button", { name: "Confirm" });
        expect(confirm).toBeDisabled();
        expect(sms).not.toHaveBeenCalled();
        fireEvent.change(input, { target: { value: "  1234  " } });
        expect(confirm).toBeEnabled();
        const confirmation = user.click(confirm);
        expect(await screen.findByText("Syncing…")).toBeInTheDocument();
        finishSync({
            status: "connected",
            inserted: 3,
            skipped: 1,
            dateFrom: "2026-07-01",
            dateTo: "2026-07-02",
        });
        await confirmation;
        await waitFor(() => expect(sms).toHaveBeenCalledWith(7, "1234"));
        expect(await screen.findByText(/3 new, 1 duplicates skipped/)).toBeInTheDocument();
    });

    it("formats Yandex Pay SMS codes and submits digits only", async () => {
        const yandexPay = { ...connector, bank: "yandex_pay" };
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([yandexPay]);
        vi.spyOn(useStore.getState(), "createConnection").mockResolvedValue({ id: 7 });
        vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        vi.spyOn(useStore.getState(), "syncConnection").mockResolvedValue({
            status: "awaiting_sms",
            message: "code:Enter the code sent by Yandex via SMS.",
        });
        const sms = vi.spyOn(useStore.getState(), "submitConnectionSms").mockResolvedValue({
            status: "connected",
            inserted: 0,
            skipped: 0,
        });
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await user.type(await screen.findByLabelText("Login"), "alice");
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "40817");
        await user.click(screen.getByRole("button", { name: "Connect & sync" }));
        const input = await screen.findByLabelText("SMS code");
        expect(input).toHaveAttribute("inputmode", "numeric");
        expect(input).toHaveAttribute("maxlength", "7");
        expect(input).toHaveAttribute("placeholder", "000-000");
        expect(screen.getByRole("button", { name: "Resend SMS (01:00)" })).toBeDisabled();
        await user.type(input, "90a1");
        expect(input).toHaveValue("901");
        await user.type(input, "05");
        expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
        await user.type(input, "37");
        expect(input).toHaveValue("901-053");
        expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
        fireEvent.change(input, { target: { value: "1234567" } });
        expect(input).toHaveValue("123-456");
        await user.click(screen.getByRole("button", { name: "Confirm" }));
        await waitFor(() => expect(sms).toHaveBeenCalledWith(7, "123456"));
    });

    it("renders a Yandex CAPTCHA challenge", async () => {
        const yandexPay = { ...connector, bank: "yandex_pay" };
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([yandexPay]);
        vi.spyOn(useStore.getState(), "createConnection").mockResolvedValue({ id: 7 });
        vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        vi.spyOn(useStore.getState(), "syncConnection").mockResolvedValue({
            status: "awaiting_sms",
            message: "captcha:https://ext.captcha.yandex.net/image?key=test",
        });
        vi.spyOn(useStore.getState(), "submitConnectionSms")
            .mockResolvedValueOnce({
                status: "awaiting_sms",
                message: "captcha:https://ext.captcha.yandex.net/image?key=next",
            })
            .mockResolvedValueOnce({ status: "awaiting_sms", message: "captcha:" });
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await user.type(await screen.findByLabelText("Login"), "alice");
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "40817");
        await user.click(screen.getByRole("button", { name: "Connect & sync" }));
        expect(await screen.findByRole("img", { name: "Yandex CAPTCHA" })).toHaveAttribute(
            "src",
            "https://ext.captcha.yandex.net/image?key=test",
        );
        expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
        await user.click(screen.getByRole("button", { name: "Show another CAPTCHA" }));
        await waitFor(() =>
            expect(useStore.getState().submitConnectionSms).toHaveBeenLastCalledWith(
                7,
                "__refresh_captcha__",
            ),
        );
        expect(await screen.findByText("A new CAPTCHA is shown.")).toBeInTheDocument();
        await user.type(screen.getByLabelText("CAPTCHA"), "wrong");
        expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
        await user.click(screen.getByRole("button", { name: "Confirm" }));
        expect(await screen.findByText(/Yandex issued a new CAPTCHA/)).toBeInTheDocument();
        expect(screen.queryByText(/captcha:https:/)).not.toBeInTheDocument();
        expect(screen.queryByRole("img", { name: "Yandex CAPTCHA" })).not.toBeInTheDocument();
        expect(screen.getByLabelText("CAPTCHA")).toHaveValue("");
        await user.type(screen.getByLabelText("CAPTCHA"), "next answer");
        expect(screen.queryByText(/Yandex issued a new CAPTCHA/)).not.toBeInTheDocument();
    });

    it("moves from CAPTCHA to a Yandex code challenge without a rejection error", async () => {
        const yandexPay = { ...connector, bank: "yandex_pay" };
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([yandexPay]);
        vi.spyOn(useStore.getState(), "createConnection").mockResolvedValue({ id: 7 });
        vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        vi.spyOn(useStore.getState(), "syncConnection").mockResolvedValue({
            status: "awaiting_sms",
            message: "captcha:https://ext.captcha.yandex.net/image?key=test",
        });
        vi.spyOn(useStore.getState(), "submitConnectionSms").mockResolvedValue({
            status: "awaiting_sms",
            message: "code:Enter the code sent by Yandex via SMS.",
        });
        const { container, unmount, user } = renderUI(
            <ConnectionDialog account={account} onClose={vi.fn()} />,
        );
        await user.type(await screen.findByLabelText("Login"), "alice");
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "40817");
        await user.click(screen.getByRole("button", { name: "Connect & sync" }));
        await user.type(await screen.findByLabelText("CAPTCHA"), "answer");
        vi.useFakeTimers();
        try {
            const clearTimer = vi.spyOn(window, "clearTimeout");
            await act(async () => fireEvent.click(screen.getByRole("button", { name: "Confirm" })));
            expect(screen.getByText("Enter the code sent by Yandex via SMS.")).toBeInTheDocument();
            expect(screen.getByLabelText("SMS code")).toBeInTheDocument();
            expect(screen.queryByText(/rejected/)).not.toBeInTheDocument();
            expect(container.querySelector(".t-danger")).toBeNull();
            expect(screen.getByRole("button", { name: "Resend SMS (01:00)" })).toBeDisabled();
            await act(() => vi.advanceTimersByTimeAsync(1000));
            expect(clearTimer).toHaveBeenCalled();
            expect(screen.getByRole("button", { name: "Resend SMS (00:59)" })).toBeDisabled();
            for (let second = 0; second < 59; second += 1) {
                await act(() => vi.advanceTimersByTimeAsync(1000));
            }
            expect(vi.getTimerCount()).toBe(0);
            const enabledResend = screen.getByRole("button", { name: "Resend SMS" });
            expect(enabledResend).toBeEnabled();
            await act(async () => fireEvent.click(enabledResend));
            expect(useStore.getState().submitConnectionSms).toHaveBeenLastCalledWith(
                7,
                "__resend_yandex_code__",
            );
            expect(screen.queryByText(/rejected/)).not.toBeInTheDocument();
            expect(screen.queryByText(/code:Enter/)).not.toBeInTheDocument();
            expect(screen.getByRole("button", { name: "Resend SMS (01:00)" })).toBeDisabled();
            const timersBeforeUnmount = vi.getTimerCount();
            expect(timersBeforeUnmount).toBeGreaterThan(0);
            unmount();
            expect(vi.getTimerCount()).toBe(timersBeforeUnmount - 1);
        } finally {
            vi.useRealTimers();
        }
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
            accounts: [
                {
                    accountId: 1,
                    inserted: 1,
                    skipped: 1,
                    batchId: null,
                    dateFrom: null,
                    dateTo: null,
                },
                {
                    accountId: 2,
                    inserted: 1,
                    skipped: 2,
                    batchId: null,
                    dateFrom: null,
                    dateTo: null,
                },
            ],
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

    it("does not treat whitespace-only credentials or bank references as complete", async () => {
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        const { user } = renderUI(<ConnectionDialog account={account} onClose={vi.fn()} />);
        await screen.findByLabelText("Login");
        const connect = screen.getByRole("button", { name: "Connect & sync" });
        await user.type(screen.getByLabelText("Login"), "   ");
        expect(connect).toBeDisabled();
        await user.clear(screen.getByLabelText("Login"));
        await user.type(screen.getByLabelText("Login"), "alice");
        expect(connect).not.toBeDisabled();
        await user.clear(screen.getByLabelText("Bank account"));
        await user.type(screen.getByLabelText("Bank account"), "   ");
        expect(connect).toBeDisabled();
    });

    it("keeps a usable saved bank reference visible when its connector is unavailable", async () => {
        seed({ accounts: [{ ...account, bankRef: "40817" }] });
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([]);
        renderUI(
            <ConnectionDialog
                account={{ ...account, bankRef: "40817" }}
                connection={{
                    id: 9,
                    bank: "removed-bank",
                    kind: "api",
                    status: "disconnected",
                    lastSync: null,
                    lastError: "Connector was removed",
                }}
                onClose={vi.fn()}
            />,
        );
        expect(await screen.findByText("40817")).toBeInTheDocument();
        expect(screen.queryByLabelText("Bank account")).not.toBeInTheDocument();
        expect(screen.getByText("Connector was removed")).toBeInTheDocument();
    });

    it("keeps OTP open after rejection, cancels it on close, and retries sync errors", async () => {
        vi.spyOn(api, "connectionsAvailable").mockResolvedValue([connector]);
        vi.spyOn(useStore.getState(), "createConnection").mockResolvedValue({ id: 7 });
        vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        const sync = vi
            .spyOn(useStore.getState(), "syncConnection")
            .mockResolvedValueOnce({ status: "awaiting_sms" })
            .mockRejectedValueOnce(new Error("network"));
        vi.spyOn(useStore.getState(), "submitConnectionSms")
            .mockResolvedValueOnce({ status: "awaiting_sms" })
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
        expect(
            await screen.findByText("The bank rejected the code — try again."),
        ).toBeInTheDocument();
        await user.type(screen.getByLabelText("SMS code"), "next");
        expect(screen.getByText("The bank rejected the code — try again.")).toBeInTheDocument();
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
