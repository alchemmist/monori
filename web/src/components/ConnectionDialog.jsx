import { useRef, useState } from "react";
import { Button } from "@mantine/core";
import { useStore } from "../store.js";
import { fmtDate } from "../format.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FTextInput } from "../ui/fields.jsx";
import Tag from "../ui/Tag.jsx";
import Txt from "../ui/Txt.jsx";

const BANK = { bank: "tbank", kind: "playwright", label: "T-Bank (browser sync)" };

const STATUS_THEME = {
    connected: "success",
    awaiting_sms: "warning",
    error: "danger",
    disconnected: "unknown",
};

export default function ConnectionDialog({ account, connection, onClose }) {
    const {
        createConnection,
        syncConnection,
        submitConnectionSms,
        cancelConnectionSync,
        deleteConnection,
        notify,
    } = useStore();
    const [step, setStep] = useState(connection ? "ready" : "credentials");
    const [phone, setPhone] = useState("");
    const [password, setPassword] = useState("");
    const [tbankAccount, setTbankAccount] = useState("");
    const [code, setCode] = useState("");
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState("");
    const connId = useRef(connection?.id ?? null);

    const runSync = async (id) => {
        setBusy(true);
        setError("");
        setStep("syncing");
        try {
            const res = await syncConnection(id);
            if (res.status === "awaiting_sms") setStep("sms");
            else {
                setResult(res);
                setStep("done");
            }
        } catch (e) {
            setError(String(e));
            setStep("error");
        } finally {
            setBusy(false);
        }
    };

    const connect = async () => {
        if (!phone.trim() || !password) return;
        setBusy(true);
        setError("");
        try {
            const conn = await createConnection({
                accountId: account.id,
                bank: BANK.bank,
                kind: BANK.kind,
                credentials: {
                    phone: phone.trim(),
                    password,
                    account: tbankAccount.trim() || null,
                },
            });
            connId.current = conn.id;
            await runSync(conn.id);
        } catch (e) {
            setError(String(e));
            setStep("error");
            setBusy(false);
        }
    };

    const confirmSms = async () => {
        if (!code.trim()) return;
        setBusy(true);
        setError("");
        setStep("syncing");
        try {
            const res = await submitConnectionSms(connId.current, code.trim());
            if (res.status === "awaiting_sms") {
                setCode("");
                setError(res.message || "The bank rejected the code — try again.");
                setStep("sms");
            } else {
                setResult(res);
                setStep("done");
            }
        } catch (e) {
            setError(String(e));
            setStep("error");
        } finally {
            setBusy(false);
        }
    };

    const disconnect = async () => {
        setBusy(true);
        try {
            await deleteConnection(connection.id);
            notify({ title: "Bank disconnected", theme: "info" });
            onClose();
        } catch (e) {
            notify({ title: "Failed to disconnect", theme: "danger", content: String(e) });
            setBusy(false);
        }
    };

    // closing mid-OTP abandons the parked login on the server so its browser
    // session doesn't leak
    const handleClose = () => {
        if (step === "sms" && connId.current) {
            cancelConnectionSync(connId.current).catch(() => {});
        }
        onClose();
    };

    let footer = { apply: "Close", onApply: handleClose, applyProps: {} };
    let body = null;

    if (step === "credentials") {
        body = (
            <>
                <Txt tone="secondary" caption>
                    Connects to {BANK.label} in a headless browser and pulls your operations.
                    Automated access to your own account is a grey area under the bank's terms — use
                    it at your own risk. Your phone and password are stored encrypted on this server
                    and used only by it to log in to the bank as you.
                </Txt>
                <FTextInput
                    label="Phone"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    autoFocus
                />
                <FTextInput
                    label="Password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                />
                <FTextInput
                    label="T-Bank account number (optional)"
                    placeholder="e.g. 5858870594 — leave empty to sync the default feed"
                    value={tbankAccount}
                    onChange={(e) => setTbankAccount(e.target.value)}
                    title="The number from the account's operations link in the cabinet; scopes the sync to that one account."
                />
            </>
        );
        footer = {
            apply: "Connect & sync",
            onApply: connect,
            applyProps: { loading: busy, disabled: !phone.trim() || !password },
        };
    } else if (step === "ready") {
        body = (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Txt tone="secondary">Status</Txt>
                    <Tag theme={STATUS_THEME[connection.status] ?? "unknown"}>
                        {connection.status}
                    </Tag>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <Txt tone="secondary">Last sync</Txt>
                    <span className="num">
                        {connection.lastSync ? fmtDate(connection.lastSync) : "never"}
                    </span>
                </div>
                {connection.lastError && (
                    <Txt tone="danger" caption>
                        {connection.lastError}
                    </Txt>
                )}
                <Button
                    variant="subtle"
                    data-tone="danger"
                    size="s"
                    onClick={disconnect}
                    loading={busy}
                >
                    Disconnect
                </Button>
            </div>
        );
        footer = {
            apply: "Sync now",
            onApply: () => runSync(connection.id),
            applyProps: { loading: busy },
        };
    } else if (step === "sms") {
        body = (
            <>
                <Txt tone="secondary" caption>
                    Enter the code the bank sent to your phone.
                </Txt>
                {error && (
                    <Txt tone="danger" caption>
                        {error}
                    </Txt>
                )}
                <FTextInput
                    label="SMS code"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    autoFocus
                />
            </>
        );
        footer = {
            apply: "Confirm",
            onApply: confirmSms,
            applyProps: { loading: busy, disabled: !code.trim() },
        };
    } else if (step === "syncing") {
        body = <Txt tone="secondary">Syncing…</Txt>;
        footer = { apply: "Close", onApply: onClose, applyProps: { disabled: true } };
    } else if (step === "done") {
        body = (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <Txt block>
                    {result.inserted} new, {result.skipped} duplicates skipped.
                </Txt>
                {result.dateFrom && (
                    <Txt tone="secondary" caption>
                        {fmtDate(result.dateFrom)} — {fmtDate(result.dateTo)}
                    </Txt>
                )}
            </div>
        );
    } else if (step === "error") {
        body = (
            <Txt tone="danger" caption>
                {error}
            </Txt>
        );
        footer = {
            apply: "Retry",
            onApply: () => (connId.current ? runSync(connId.current) : setStep("credentials")),
            applyProps: { loading: busy },
        };
    }

    return (
        <AppDialog
            title={`Bank sync — ${account.name}`}
            onClose={handleClose}
            applyText={footer.apply}
            onApply={footer.onApply}
            applyLoading={footer.applyProps.loading ?? false}
            applyDisabled={footer.applyProps.disabled ?? false}
            onCancel={handleClose}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                {body}
            </div>
        </AppDialog>
    );
}
