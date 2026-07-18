import { useRef, useState } from "react";
import { Button, Dialog, Label, Text, TextInput } from "@gravity-ui/uikit";
import { useStore } from "../store.js";
import { fmtDate } from "../format.js";

const BANK = { bank: "tbank", kind: "playwright", label: "T-Bank (browser sync)" };

const STATUS_THEME = {
    connected: "success",
    awaiting_sms: "warning",
    error: "danger",
    disconnected: "unknown",
};

export default function ConnectionDialog({ account, connection, onClose }) {
    const { createConnection, syncConnection, submitConnectionSms, deleteConnection, notify } =
        useStore();
    const [step, setStep] = useState(connection ? "ready" : "credentials");
    const [phone, setPhone] = useState("");
    const [password, setPassword] = useState("");
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
                credentials: { phone: phone.trim(), password },
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
            setResult(res);
            setStep("done");
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

    let footer = { apply: "Close", onApply: onClose, applyProps: {} };
    let body = null;

    if (step === "credentials") {
        body = (
            <>
                <Text color="secondary" variant="caption-2">
                    Connects to {BANK.label} in a headless browser and pulls your operations.
                    Automated access to your own account is a grey area under the bank's terms — use
                    it at your own risk. Your phone and password are stored encrypted on this server
                    and never leave it.
                </Text>
                <TextInput label="Phone" value={phone} onUpdate={setPhone} autoFocus />
                <TextInput
                    label="Password"
                    type="password"
                    value={password}
                    onUpdate={setPassword}
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
                    <Text color="secondary">Status</Text>
                    <Label theme={STATUS_THEME[connection.status] ?? "unknown"}>
                        {connection.status}
                    </Label>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <Text color="secondary">Last sync</Text>
                    <span className="num">
                        {connection.lastSync ? fmtDate(connection.lastSync) : "never"}
                    </span>
                </div>
                {connection.lastError && (
                    <Text color="danger" variant="caption-2">
                        {connection.lastError}
                    </Text>
                )}
                <Button view="flat-danger" size="s" onClick={disconnect} loading={busy}>
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
                <Text color="secondary" variant="caption-2">
                    Enter the code the bank sent to your phone.
                </Text>
                <TextInput label="SMS code" value={code} onUpdate={setCode} autoFocus />
            </>
        );
        footer = {
            apply: "Confirm",
            onApply: confirmSms,
            applyProps: { loading: busy, disabled: !code.trim() },
        };
    } else if (step === "syncing") {
        body = <Text color="secondary">Syncing…</Text>;
        footer = { apply: "Close", onApply: onClose, applyProps: { disabled: true } };
    } else if (step === "done") {
        body = (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <Text>
                    {result.inserted} new, {result.skipped} duplicates skipped.
                </Text>
                {result.dateFrom && (
                    <Text color="secondary" variant="caption-2">
                        {fmtDate(result.dateFrom)} — {fmtDate(result.dateTo)}
                    </Text>
                )}
            </div>
        );
    } else if (step === "error") {
        body = (
            <Text color="danger" variant="caption-2">
                {error}
            </Text>
        );
        footer = {
            apply: "Retry",
            onApply: () => (connId.current ? runSync(connId.current) : setStep("credentials")),
            applyProps: { loading: busy },
        };
    }

    return (
        <Dialog open onClose={onClose} size="s">
            <Dialog.Header caption={`Bank sync — ${account.name}`} />
            <Dialog.Body>
                <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                    {body}
                </div>
            </Dialog.Body>
            <Dialog.Footer
                textButtonApply={footer.apply}
                textButtonCancel="Cancel"
                onClickButtonApply={footer.onApply}
                onClickButtonCancel={onClose}
                propsButtonApply={footer.applyProps}
            />
        </Dialog>
    );
}
