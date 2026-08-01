import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@mantine/core";
import { useStore } from "../store.js";
import { api } from "../api.js";
import { fmtDate } from "../format.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FSelect, FTextInput } from "../ui/fields.jsx";
import Tag from "../ui/Tag.jsx";
import Txt from "../ui/Txt.jsx";
import type { Account, AvailableConnector, Connection, Id, SyncResult } from "../types.js";

const STATUS_THEME: Record<string, string> = {
    connected: "success",
    awaiting_sms: "warning",
    error: "danger",
    disconnected: "unknown",
};

const NEW_LOGIN = "new";

type DialogStep = "credentials" | "ready" | "syncing" | "sms" | "done" | "error";
interface DialogFooter {
    apply: string;
    onApply: () => void | Promise<void>;
    applyProps: { loading?: boolean; disabled?: boolean };
}

type ConnectionAccount = Pick<Account, "id" | "name"> & Partial<Pick<Account, "bankRef">>;
type ConnectionSummary = Pick<Connection, "id" | "bank" | "kind" | "status" | "lastSync"> &
    Partial<Pick<Connection, "lastError">>;

export default function ConnectionDialog({
    account,
    connection,
    onClose,
}: {
    account: ConnectionAccount;
    connection?: ConnectionSummary | null;
    onClose: () => void;
}) {
    const {
        createConnection,
        syncConnection,
        submitConnectionSms,
        cancelConnectionSync,
        deleteConnection,
        patchAccount,
        notify,
    } = useStore();
    const connections = useStore((s) => s.snapshot?.connections ?? []);
    // the `account` prop is captured when the dialog opens; read the live row
    // from the store so a saved bankRef resets the dirty check without a reopen
    const liveAccount =
        useStore((s) => s.snapshot?.accounts?.find((a) => a.id === account.id)) ?? account;
    const [connectors, setConnectors] = useState<AvailableConnector[]>([]);
    const [bankKey, setBankKey] = useState<string | null>(null);
    const [loginChoice, setLoginChoice] = useState(NEW_LOGIN);
    const [credentials, setCredentials] = useState<Record<string, string>>({});
    const [accountFields, setAccountFields] = useState<Record<string, string>>({
        account: account.bankRef || "",
    });
    const [step, setStep] = useState<DialogStep>(connection ? "ready" : "credentials");
    const [code, setCode] = useState("");
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState<SyncResult | null>(null);
    const [error, setError] = useState("");
    const connId = useRef<Id | null>(connection?.id ?? null);

    useEffect(() => {
        api.connectionsAvailable()
            .then((list) => {
                setConnectors(list);
                if (list.length === 1) setBankKey(`${list[0]!.bank}/${list[0]!.kind}`);
            })
            .catch((e) =>
                notify({ title: "Failed to load banks", theme: "danger", content: String(e) }),
            );
    }, [notify]);

    const connector = connectors.find((c) => `${c.bank}/${c.kind}` === bankKey) ?? null;
    const existingLogins = connector
        ? connections.filter((c) => c.bank === connector.bank && c.kind === connector.kind)
        : [];
    const needsCredentials = loginChoice === NEW_LOGIN;
    const credentialsComplete =
        connector &&
        connector.connectionParams.every(
            (p) => !p.required || String(credentials[p.name] ?? "").trim(),
        );
    const accountComplete = (c: AvailableConnector | null) =>
        !c ||
        c.accountParams.every((p) => !p.required || String(accountFields[p.name] ?? "").trim());

    const runSync = async (id: Id) => {
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
        if (!connector) return;
        setBusy(true);
        setError("");
        try {
            let id: Id;
            if (needsCredentials) {
                const conn = await createConnection({
                    bank: connector.bank,
                    kind: connector.kind,
                    credentials: Object.fromEntries(
                        connector.connectionParams.map((p) => [
                            p.name,
                            String(credentials[p.name] ?? "").trim(),
                        ]),
                    ),
                });
                id = conn.id;
            } else {
                id = Number(loginChoice);
            }
            connId.current = id;
            const ref = String(accountFields["account"] ?? "").trim();
            await patchAccount(account.id, { connectionId: id, bankRef: ref });
            await runSync(id);
        } catch (e) {
            setError(String(e));
            setStep("error");
            setBusy(false);
        }
    };

    const confirmSms = async () => {
        if (!code.trim() || connId.current == null) return;
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

    // the connector of an existing connection (the credentials-step `connector`
    // is keyed on the bank picker, which is untouched in the ready step)
    const readyConnector = connection
        ? (connectors.find((c) => c.bank === connection.bank && c.kind === connection.kind) ?? null)
        : null;
    const refDirty = String(accountFields["account"] ?? "").trim() !== (liveAccount.bankRef || "");

    const saveRef = async () => {
        setBusy(true);
        try {
            await patchAccount(account.id, {
                bankRef: String(accountFields["account"] ?? "").trim(),
            });
            return true;
        } catch (e) {
            notify({ title: "Failed to save bank account", theme: "danger", content: String(e) });
            return false;
        } finally {
            setBusy(false);
        }
    };

    const unlink = async () => {
        setBusy(true);
        try {
            await patchAccount(account.id, { connectionId: 0 });
            notify({ title: "Account unlinked", theme: "info" });
            onClose();
        } catch (e) {
            notify({ title: "Failed to unlink", theme: "danger", content: String(e) });
            setBusy(false);
        }
    };

    const disconnect = async () => {
        if (!connection) return;
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

    // unlink/disconnect refresh the snapshot before onClose runs, so the
    // connection prop can vanish while the dialog is still mounted — render
    // nothing instead of crashing on connection.status, and actively close so
    // the parent's dialog state is cleared even when the connection vanished
    // for an external reason (another tab's sync, a background refresh)
    const gone = step === "ready" && !connection;
    useEffect(() => {
        if (gone) onClose();
    }, [gone, onClose]);
    if (gone) return null;

    let footer: DialogFooter = { apply: "Close", onApply: handleClose, applyProps: {} };
    let body: ReactNode = null;

    if (step === "credentials") {
        body = (
            <>
                <FSelect
                    label="Bank"
                    placeholder="Pick a bank"
                    value={bankKey}
                    onChange={setBankKey}
                    data={connectors.map((c) => ({
                        value: `${c.bank}/${c.kind}`,
                        label: c.label,
                    }))}
                />
                {connector && (
                    <Txt tone="secondary" caption>
                        Connects to {connector.label} in a headless browser and pulls your
                        operations. Automated access to your own account is a grey area under the
                        bank's terms — use it at your own risk. Credentials are stored encrypted on
                        this server and used only by it to log in to the bank as you.
                    </Txt>
                )}
                {connector && existingLogins.length > 0 && (
                    <FSelect
                        label="Bank login"
                        value={loginChoice}
                        onChange={(v) => setLoginChoice(v ?? NEW_LOGIN)}
                        data={[
                            { value: NEW_LOGIN, label: "New login…" },
                            ...existingLogins.map((c) => ({
                                value: String(c.id),
                                label: `${connector.label} login #${c.id}`,
                            })),
                        ]}
                    />
                )}
                {connector &&
                    needsCredentials &&
                    connector.connectionParams.map((p) => (
                        <FTextInput
                            key={p.name}
                            label={p.label}
                            type={p.secret ? "password" : "text"}
                            value={credentials[p.name] ?? ""}
                            onChange={(e) =>
                                setCredentials((prev) => ({ ...prev, [p.name]: e.target.value }))
                            }
                        />
                    ))}
                {connector &&
                    connector.accountParams.map((p) => (
                        <FTextInput
                            key={p.name}
                            label={p.label}
                            placeholder={p.help}
                            title={p.help}
                            value={accountFields[p.name] ?? ""}
                            onChange={(e) =>
                                setAccountFields((prev) => ({
                                    ...prev,
                                    [p.name]: e.target.value,
                                }))
                            }
                        />
                    ))}
            </>
        );
        footer = {
            apply: "Connect & sync",
            onApply: connect,
            applyProps: {
                loading: busy,
                disabled:
                    !connector ||
                    (needsCredentials && !credentialsComplete) ||
                    !accountComplete(connector),
            },
        };
    } else if (step === "ready") {
        if (!connection) return null;
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
                {readyConnector
                    ? readyConnector.accountParams.map((p) => (
                          <FTextInput
                              key={p.name}
                              label={p.label}
                              placeholder={p.help}
                              title={p.help}
                              value={accountFields[p.name] ?? ""}
                              onChange={(e) =>
                                  setAccountFields((prev) => ({
                                      ...prev,
                                      [p.name]: e.target.value,
                                  }))
                              }
                          />
                      ))
                    : liveAccount.bankRef && (
                          <div style={{ display: "flex", justifyContent: "space-between" }}>
                              <Txt tone="secondary">Bank account</Txt>
                              <span className="num">{liveAccount.bankRef}</span>
                          </div>
                      )}
                {refDirty && (
                    <div>
                        <Button
                            variant="subtle"
                            size="s"
                            onClick={() => void saveRef()}
                            loading={busy}
                            disabled={!accountComplete(readyConnector)}
                        >
                            Save bank account
                        </Button>
                    </div>
                )}
                {connection.lastError && (
                    <Txt tone="danger" caption>
                        {connection.lastError}
                    </Txt>
                )}
                <div style={{ display: "flex", gap: 8 }}>
                    <Button variant="subtle" size="s" onClick={() => void unlink()} loading={busy}>
                        Unlink account
                    </Button>
                    <Button
                        variant="subtle"
                        data-tone="danger"
                        size="s"
                        onClick={() => void disconnect()}
                        loading={busy}
                    >
                        Disconnect bank
                    </Button>
                </div>
            </div>
        );
        footer = {
            apply: "Sync now",
            onApply: async () => {
                if (refDirty && !(await saveRef())) return;
                await runSync(connection.id);
            },
            applyProps: { loading: busy, disabled: !accountComplete(readyConnector) },
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
        if (!result) return null;
        const unmappedTails = result.unmappedTails ?? [];
        body = (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <Txt block>
                    {result.inserted} new, {result.skipped} duplicates skipped
                    {result.accounts && result.accounts.length > 1
                        ? ` across ${result.accounts.length} accounts`
                        : ""}
                    .
                </Txt>
                {result.dateFrom && result.dateTo && (
                    <Txt tone="secondary" caption>
                        {fmtDate(result.dateFrom)} — {fmtDate(result.dateTo)}
                    </Txt>
                )}
                {unmappedTails.length > 0 && (
                    <Txt tone="warning" caption block>
                        Cards not bound to any account:{" "}
                        {unmappedTails.map((u) => `*${u.tail} (${u.rows} rows)`).join(", ")}. Their
                        rows landed on this account — add each tail to its account (Accounts → Edit
                        → Card tails) to route them automatically.
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
            onApply={() => void footer.onApply()}
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
