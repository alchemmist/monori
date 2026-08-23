import { useRef, useState } from "react";
import { Button } from "@mantine/core";
import { Checkbox } from "@mantine/core";
import { api } from "../api.js";
import { readStatementFile, statementTails, tailMatches } from "../importFile.js";
import { useStore } from "../store.js";
import { money, fmtDate } from "../format.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FSelect, FTextArea } from "../ui/fields.jsx";
import Tag from "../ui/Tag.jsx";
import Txt from "../ui/Txt.jsx";
import type { ImportPreview } from "../types.js";

const readLastAccount = () => {
    try {
        return localStorage.getItem("import_last_account") ?? "";
    } catch {
        return "";
    }
};

export default function ImportDialog({ onClose }: { onClose: () => void }) {
    const { snapshot, user, commitImport, patchAccount, notify } = useStore();
    if (!snapshot) throw new Error("Import requires a loaded snapshot");
    const accounts = snapshot.accounts.filter((a) => !a.archived);
    const preset = user?.defaultAccountId;
    const [text, setText] = useState("");
    const [preview, setPreview] = useState<ImportPreview | null>(null);
    const [busy, setBusy] = useState(false);
    const [detectedTail, setDetectedTail] = useState<string | null>(null);
    const [rememberTail, setRememberTail] = useState(true);
    const fileRef = useRef<HTMLInputElement>(null);
    const [account, setAccount] = useState(() => {
        // the settings-level default wins over the last manual pick: it exists
        // for the statements whose account nothing in the file can tell
        if (preset != null && accounts.some((a) => a.id === preset)) return String(preset);
        const last = readLastAccount();
        if (last !== "" && accounts.some((a) => String(a.id) === last)) return last;
        return accounts[0] ? String(accounts[0].id) : "";
    });
    const catName = new Map(snapshot.categories.map((c) => [c.id, c.name]));

    const runPreview = async (source: string = text) => {
        setBusy(true);
        try {
            let accId = +account;
            let p = await api.importPreview(source, accId);
            // route the statement to the account that owns its card tail; the
            // duplicate flags are account-specific, so a switch re-previews
            const tails = statementTails(p.rows);
            if (tails.length === 1) {
                const owners = accounts.filter((a) =>
                    (a.cardTails ?? []).some((t) => tailMatches(t, tails[0]!)),
                );
                if (owners.length === 1 && owners[0]!.id !== accId) {
                    accId = owners[0]!.id;
                    setAccount(String(accId));
                    p = await api.importPreview(source, accId);
                }
            }
            setDetectedTail(tails.length === 1 ? tails[0]! : null);
            setPreview(p);
        } catch (e) {
            notify({ title: "Preview failed", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    const pickFile = async (file?: File) => {
        if (file == null) return;
        try {
            const decoded = await readStatementFile(file);
            setText(decoded);
            await runPreview(decoded);
        } catch (e) {
            notify({ title: "Could not read the file", theme: "danger", content: String(e) });
        } finally {
            if (fileRef.current) fileRef.current.value = "";
        }
    };

    const fresh = preview?.rows.filter((r) => r.duplicate !== true) ?? [];
    const selected = accounts.find((a) => String(a.id) === account);
    // offer to bind the tail only while NO account owns it — remembering a
    // tail that already belongs elsewhere would make future routing ambiguous
    const tailOwners =
        detectedTail != null && detectedTail !== ""
            ? accounts.filter((a) => (a.cardTails ?? []).some((t) => tailMatches(t, detectedTail)))
            : [];
    const offerRemember =
        preview != null &&
        detectedTail != null &&
        detectedTail !== "" &&
        selected != null &&
        tailOwners.length === 0;

    const commit = async () => {
        setBusy(true);
        try {
            const { inserted } = await commitImport(fresh);
            if (offerRemember && rememberTail) {
                await patchAccount(+account, {
                    cardTails: [...(selected.cardTails ?? []), detectedTail],
                }).catch(() => {});
            }
            try {
                localStorage.setItem("import_last_account", account);
            } catch {
                /* storage unavailable — remembering the account is best-effort */
            }
            notify({ title: `Imported ${inserted} transactions`, theme: "success" });
            onClose();
        } catch (e) {
            notify({ title: "Import failed", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title="Import bank statement"
            onClose={onClose}
            size="l"
            applyText={preview == null ? "Preview" : `Import ${fresh.length}`}
            onApply={() => void (preview == null ? runPreview() : commit())}
            applyLoading={busy}
            applyDisabled={
                account === "" || (preview == null ? text.trim() === "" : fresh.length === 0)
            }
            cancelText={preview == null ? "Cancel" : "Back"}
            onCancel={preview == null ? onClose : () => setPreview(null)}
        >
            <div style={{ marginBottom: 14, display: "flex", alignItems: "center", gap: 10 }}>
                <Txt tone="secondary">Import into</Txt>
                <FSelect
                    value={account === "" ? null : account}
                    onChange={(v) => {
                        setAccount(v);
                        // duplicate flags are account-specific — force a re-preview
                        setPreview(null);
                    }}
                    data={accounts.map((a) => ({ value: String(a.id), label: a.name }))}
                    style={{ width: 200 }}
                />
            </div>
            {preview == null ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <input
                        ref={fileRef}
                        type="file"
                        accept=".csv,text/csv"
                        style={{ display: "none" }}
                        onChange={(e) => void pickFile(e.target.files?.[0])}
                    />
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <Button
                            variant="default"
                            loading={busy}
                            onClick={() => fileRef.current?.click()}
                        >
                            Upload bank CSV
                        </Button>
                        <Txt tone="secondary" caption>
                            the bank's CSV export, UTF-8 or windows-1251
                        </Txt>
                    </div>
                    <Txt tone="secondary" block>
                        …or paste statement rows exactly as you used to paste them into the sheet —
                        tab- or semicolon-separated, dates as dd.mm.yyyy, decimal commas.
                    </Txt>
                    <FTextArea
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        autosize
                        minRows={12}
                        maxRows={16}
                        placeholder={
                            "03.07.2026 19:48:24\t03.07.2026\t*2947\tOK\t-450,00\tRUB\t..."
                        }
                    />
                </div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ display: "flex", gap: 8 }}>
                        <Tag theme="success">{fresh.length} new</Tag>
                        <Tag theme="warning">
                            {preview.rows.length - fresh.length} duplicates skipped
                        </Tag>
                        {preview.errors.length > 0 && (
                            <Tag theme="danger">{preview.errors.length} unparsed lines</Tag>
                        )}
                    </div>
                    {offerRemember && (
                        <Checkbox
                            size="sm"
                            checked={rememberTail}
                            onChange={(e) => setRememberTail(e.currentTarget.checked)}
                            label={`Remember card *${detectedTail} for ${selected.name}`}
                        />
                    )}
                    <div style={{ maxHeight: 360, overflow: "auto" }}>
                        <table className="budget-grid">
                            <thead>
                                <tr>
                                    <th style={{ textAlign: "left" }}>Date</th>
                                    <th style={{ textAlign: "left" }}>Description</th>
                                    <th>Amount</th>
                                    <th style={{ textAlign: "left" }}>Category</th>
                                </tr>
                            </thead>
                            <tbody>
                                {preview.rows.map((r, i) => (
                                    <tr key={i} style={{ opacity: r.duplicate === true ? 0.4 : 1 }}>
                                        <td style={{ textAlign: "left" }} className="num">
                                            {fmtDate(r.date)}
                                        </td>
                                        <td style={{ textAlign: "left" }}>{r.description}</td>
                                        <td>
                                            <span
                                                className={`money num ${r.amount > 0 ? "money_pos" : ""}`}
                                            >
                                                {money(r.amount)}
                                            </span>
                                        </td>
                                        <td style={{ textAlign: "left" }}>
                                            {r.duplicate === true ? (
                                                <Txt tone="secondary">duplicate</Txt>
                                            ) : r.categoryId != null ? (
                                                catName.get(r.categoryId)
                                            ) : (
                                                <Txt tone="warning">uncategorized</Txt>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {preview.errors.length > 0 && (
                        <div>
                            {preview.errors.slice(0, 5).map((e, i) => (
                                <Txt key={i} tone="danger" caption block>
                                    line {e.line}: {e.error}
                                </Txt>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </AppDialog>
    );
}
