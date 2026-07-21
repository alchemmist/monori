import { useState } from "react";
import { api } from "../api.js";
import { useStore } from "../store.js";
import { money, fmtDate } from "../format.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FSelect, FTextArea } from "../ui/fields.jsx";
import Tag from "../ui/Tag.jsx";
import Txt from "../ui/Txt.jsx";

const readLastAccount = () => {
    try {
        return localStorage.getItem("import_last_account") || "";
    } catch {
        return "";
    }
};

export default function ImportDialog({ onClose }) {
    const { snapshot, commitImport, notify } = useStore();
    const accounts = (snapshot.accounts ?? []).filter((a) => !a.archived);
    const [text, setText] = useState("");
    const [preview, setPreview] = useState(null);
    const [busy, setBusy] = useState(false);
    const [account, setAccount] = useState(() => {
        const last = readLastAccount();
        if (last && accounts.some((a) => String(a.id) === last)) return last;
        return accounts[0] ? String(accounts[0].id) : "";
    });
    const catName = new Map(snapshot.categories.map((c) => [c.id, c.name]));

    const runPreview = async () => {
        setBusy(true);
        try {
            setPreview(await api.importPreview(text, +account));
        } catch (e) {
            notify({ title: "Preview failed", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    const fresh = preview?.rows.filter((r) => !r.duplicate) ?? [];

    const commit = async () => {
        setBusy(true);
        try {
            const { inserted } = await commitImport(fresh, +account);
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
            applyText={preview ? `Import ${fresh.length}` : "Preview"}
            onApply={preview ? commit : runPreview}
            applyLoading={busy}
            applyDisabled={!account || (preview ? fresh.length === 0 : !text.trim())}
            cancelText={preview ? "Back" : "Cancel"}
            onCancel={preview ? () => setPreview(null) : onClose}
        >
            <div style={{ marginBottom: 14, display: "flex", alignItems: "center", gap: 10 }}>
                <Txt tone="secondary">Import into</Txt>
                <FSelect
                    value={account || null}
                    onChange={(v) => {
                        setAccount(v ?? "");
                        // duplicate flags are account-specific — force a re-preview
                        setPreview(null);
                    }}
                    data={accounts.map((a) => ({ value: String(a.id), label: a.name }))}
                    style={{ width: 200 }}
                />
            </div>
            {!preview ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <Txt tone="secondary" block>
                        Paste statement rows exactly as you used to paste them into the sheet — tab-
                        or semicolon-separated, dates as dd.mm.yyyy, decimal commas.
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
                                    <tr key={i} style={{ opacity: r.duplicate ? 0.4 : 1 }}>
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
                                            {r.duplicate ? (
                                                <Txt tone="secondary">duplicate</Txt>
                                            ) : r.categoryId ? (
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
