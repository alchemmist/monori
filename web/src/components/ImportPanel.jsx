import { useRef, useState } from "react";
import { Button } from "@mantine/core";
import { api } from "../api.js";
import { readStatementFile } from "../importFile.js";
import { useStore } from "../store.js";
import { money, fmtDate } from "../format.js";
import InlineSelect from "../ui/InlineSelect.jsx";
import Tab from "../ui/Tab.jsx";
import Tag from "../ui/Tag.jsx";
import Txt from "../ui/Txt.jsx";
import "./ImportPanel.css";

/* A statement is reviewed in a wide tab, rather than a dialog, because a
 * mixed-card CSV needs several decisions at once. The tab can be collapsed to
 * create an account or inspect the ledger without throwing the import away. */
export default function ImportPanel({ onClose }) {
    const { snapshot, commitImport, notify } = useStore();
    const accounts = (snapshot.accounts ?? []).filter((a) => !a.archived);
    const categories = (snapshot.categories ?? []).filter((c) => !c.archived);
    const fileRef = useRef(null);
    const [fileName, setFileName] = useState("");
    const [rows, setRows] = useState(null);
    const [errors, setErrors] = useState([]);
    const [busy, setBusy] = useState(false);

    const accountOptions = accounts.map((a) => ({ value: String(a.id), label: a.name }));
    const categoryOptions = [
        { value: "", label: "Uncategorized" },
        ...categories.map((c) => ({ value: String(c.id), label: c.name })),
    ];
    const unassigned = rows?.filter((r) => r.accountId == null).length ?? 0;
    const fresh = rows?.filter((r) => !r.duplicate).length ?? 0;
    const allAssigned = Boolean(rows?.length) && unassigned === 0;

    const preview = async (source) => {
        setBusy(true);
        try {
            const p = await api.importPreview(source);
            setRows(p.rows);
            setErrors(p.errors);
        } catch (e) {
            notify({ title: "Preview failed", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    const pickFile = async (file) => {
        if (!file) return;
        try {
            const decoded = await readStatementFile(file);
            setFileName(file.name);
            await preview(decoded);
        } catch (e) {
            notify({ title: "Could not read the file", theme: "danger", content: String(e) });
        } finally {
            if (fileRef.current) fileRef.current.value = "";
        }
    };

    const changeRow = (index, patch) =>
        setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));

    const commit = async () => {
        if (!allAssigned) return;
        setBusy(true);
        try {
            const { inserted } = await commitImport(rows);
            notify({ title: `Imported ${inserted} transactions`, theme: "success" });
            onClose();
        } catch (e) {
            notify({ title: "Import failed", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    const footer = (
        <>
            <Button size="l" variant="subtle" onClick={onClose}>
                Cancel
            </Button>
            <Button
                size="l"
                variant="filled"
                loading={busy && !!rows}
                disabled={!allAssigned}
                onClick={commit}
            >
                Import {fresh}
            </Button>
        </>
    );

    return (
        <Tab
            title="Import bank statement"
            strip="Import"
            width={86}
            persistKey="statement-import"
            onClose={onClose}
            footer={footer}
        >
            <input
                ref={fileRef}
                type="file"
                accept=".csv,text/csv"
                style={{ display: "none" }}
                onChange={(e) => pickFile(e.target.files?.[0])}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <Button
                    variant="default"
                    loading={busy && !rows}
                    onClick={() => fileRef.current?.click()}
                >
                    {fileName ? "Choose another CSV" : "Upload bank CSV"}
                </Button>
                {fileName && <Txt tone="secondary">{fileName}</Txt>}
                <Txt tone="secondary" caption>
                    UTF-8 or windows-1251
                </Txt>
            </div>

            {!rows ? (
                <div className="import-preview" style={{ marginTop: 16 }}>
                    <Txt tone="secondary" block>
                        Upload a bank CSV. Transactions are matched to accounts by the card tails
                        configured on each account.
                    </Txt>
                </div>
            ) : (
                <div className="import-preview" style={{ marginTop: 16 }}>
                    <div
                        style={{
                            display: "flex",
                            gap: 8,
                            alignItems: "center",
                            flexWrap: "wrap",
                            marginBottom: 12,
                        }}
                    >
                        <Tag theme="success">{fresh} new</Tag>
                        <Tag theme="warning">{rows.length - fresh} duplicates skipped</Tag>
                        {unassigned > 0 && <Tag theme="danger">{unassigned} need an account</Tag>}
                        {errors.length > 0 && (
                            <Tag theme="danger">{errors.length} unparsed lines</Tag>
                        )}
                        {unassigned > 0 && (
                            <Txt tone="warning" caption>
                                Choose an account for every unassigned row before importing.
                            </Txt>
                        )}
                    </div>
                    <div className="import-preview__table">
                        <table className="budget-grid import-grid">
                            <colgroup>
                                <col className="import-col-date" />
                                <col className="import-col-description" />
                                <col className="import-col-amount" />
                                <col className="import-col-card" />
                                <col className="import-col-account" />
                                <col className="import-col-category" />
                            </colgroup>
                            <thead>
                                <tr>
                                    <th style={{ textAlign: "left" }}>Date</th>
                                    <th
                                        className="import-description-head"
                                        style={{ textAlign: "left" }}
                                    >
                                        Description
                                    </th>
                                    <th>Amount</th>
                                    <th className="import-card" style={{ textAlign: "left" }}>
                                        Card
                                    </th>
                                    <th style={{ textAlign: "left" }}>Account</th>
                                    <th className="import-category" style={{ textAlign: "left" }}>
                                        Category
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((row, index) => (
                                    <tr key={index} style={{ opacity: row.duplicate ? 0.48 : 1 }}>
                                        <td
                                            className="num import-date"
                                            style={{ textAlign: "left" }}
                                        >
                                            <span className="import-date__full">
                                                {fmtDate(row.date)}
                                            </span>
                                            <span className="import-date__short">
                                                {fmtDate(row.date).slice(0, 5)}
                                            </span>
                                        </td>
                                        <td
                                            style={{
                                                textAlign: "left",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                            }}
                                            title={row.description}
                                        >
                                            {row.description}
                                        </td>
                                        <td>
                                            <span
                                                className={`money num ${row.amount > 0 ? "money_pos" : ""}`}
                                            >
                                                {money(row.amount)}
                                            </span>
                                        </td>
                                        <td
                                            className="num import-card"
                                            style={{ textAlign: "left" }}
                                        >
                                            {row.card || "—"}
                                        </td>
                                        <td style={{ textAlign: "left" }}>
                                            <InlineSelect
                                                small
                                                searchable
                                                fullWidth
                                                value={
                                                    row.accountId == null
                                                        ? ""
                                                        : String(row.accountId)
                                                }
                                                onChange={(value) =>
                                                    changeRow(index, {
                                                        accountId: value ? Number(value) : null,
                                                    })
                                                }
                                                data={accountOptions}
                                                placeholder="Choose account"
                                            />
                                        </td>
                                        <td
                                            className="import-category"
                                            style={{ textAlign: "left" }}
                                        >
                                            <InlineSelect
                                                small
                                                searchable
                                                fullWidth
                                                value={
                                                    row.categoryId == null
                                                        ? ""
                                                        : String(row.categoryId)
                                                }
                                                onChange={(value) =>
                                                    changeRow(index, {
                                                        categoryId: value ? Number(value) : null,
                                                    })
                                                }
                                                data={categoryOptions}
                                            />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {errors.length > 0 && (
                        <div style={{ marginTop: 12 }}>
                            {errors.slice(0, 5).map((e, i) => (
                                <Txt key={i} tone="danger" caption block>
                                    line {e.line}: {e.error}
                                </Txt>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </Tab>
    );
}
