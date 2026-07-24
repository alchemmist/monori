import { useRef, useState } from "react";
import { Button, Radio } from "@mantine/core";
import { ChevronLeft, ChevronRight, Xmark } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { api } from "../api.js";
import { FSelect } from "../ui/fields.jsx";
import Txt from "../ui/Txt.jsx";

/* Side panel instead of a modal so the app stays usable mid-migration:
 * collapse it to a strip, create the missing accounts, expand and finish —
 * the chosen file and preview survive the whole time. */
export default function MigratePanel({ onClose }) {
    const accounts = useStore((s) => s.snapshot?.accounts ?? []);
    const load = useStore((s) => s.load);
    const notify = useStore((s) => s.notify);
    const fileRef = useRef(null);
    const [collapsed, setCollapsed] = useState(false);
    const [animating, setAnimating] = useState(false);

    const toggleCollapsed = (next) => {
        setCollapsed(next);
        setAnimating(true);
    };
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [mapping, setMapping] = useState({});
    const [budgetPolicy, setBudgetPolicy] = useState("overwrite");
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);

    const accountOptions = accounts
        .filter((a) => !a.archived)
        .map((a) => ({ value: String(a.id), label: a.name }));

    const pick = async (picked) => {
        if (!picked) return;
        setBusy(true);
        setPreview(null);
        setResult(null);
        try {
            const p = await api.workbookPreview(picked);
            setFile(picked);
            setPreview(p);
            setMapping({});
        } catch (e) {
            notify({ title: "Could not read workbook", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    const markers = preview?.accountMarkers ?? [];
    const allMapped = markers.every((m) => mapping[m]);

    const commit = async () => {
        setBusy(true);
        try {
            const numeric = Object.fromEntries(markers.map((m) => [m, Number(mapping[m])]));
            const r = await api.workbookCommit(file, numeric, budgetPolicy);
            setResult(r);
            await load();
        } catch (e) {
            notify({ title: "Migration failed", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    const panelClass = [
        "migrate-panel",
        collapsed && "migrate-panel_collapsed",
        animating && "migrate-panel_animating",
    ]
        .filter(Boolean)
        .join(" ");

    return (
        <aside
            className={panelClass}
            onTransitionEnd={(e) => {
                if (e.propertyName === "width") setAnimating(false);
            }}
        >
            <button
                className="migrate-panel__strip"
                onClick={() => toggleCollapsed(false)}
                title="Expand migration panel"
                aria-label="Expand migration panel"
                aria-hidden={!collapsed}
                tabIndex={collapsed ? 0 : -1}
            >
                <ChevronLeft width={16} height={16} />
                <span className="migrate-panel__strip-label">Migration</span>
            </button>
            <div className="migrate-panel__inner">
                <div className="migrate-panel__head">
                    <div className="migrate-panel__title">Migrate from spreadsheet</div>
                    <div className="migrate-panel__head-actions">
                        <button
                            className="migrate-panel__icon-btn"
                            onClick={() => toggleCollapsed(true)}
                            title="Collapse — the app stays usable, your file stays loaded"
                            aria-label="Collapse migration panel"
                        >
                            <ChevronRight width={16} height={16} />
                        </button>
                        <button
                            className="migrate-panel__icon-btn"
                            onClick={onClose}
                            title="Close"
                            aria-label="Close migration panel"
                        >
                            <Xmark width={16} height={16} />
                        </button>
                    </div>
                </div>
                <div className="migrate-panel__content">
                    <input
                        ref={fileRef}
                        type="file"
                        accept=".xlsx"
                        style={{ display: "none" }}
                        onChange={(e) => pick(e.target.files?.[0])}
                    />
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <Button
                            variant="default"
                            loading={busy && !preview}
                            onClick={() => fileRef.current?.click()}
                        >
                            {file ? "Choose another file" : "Choose .xlsx file"}
                        </Button>
                        {file && <Txt tone="secondary">{file.name}</Txt>}
                    </div>
                    {preview && !result && (
                        <>
                            <Txt>
                                {preview.groups} groups, {preview.categories} categories,{" "}
                                {preview.transactions} transactions, {preview.budgetCells} budget
                                cells
                            </Txt>
                            {preview.errors.length > 0 && (
                                <Txt tone="secondary" caption>
                                    {preview.errors.length} rows could not be parsed and will be
                                    skipped
                                </Txt>
                            )}
                            {preview.warnings.map((w) => (
                                <Txt key={w} tone="secondary" caption>
                                    {w}
                                </Txt>
                            ))}
                            {markers.length > 0 && (
                                <Txt tone="secondary" caption>
                                    Missing an account? Collapse this panel with the arrow above,
                                    create it, then come back — the file stays loaded.
                                </Txt>
                            )}
                            {markers.map((m) => (
                                <FSelect
                                    key={m || "(default)"}
                                    label={`Account for ${m || "unmarked rows"}`}
                                    placeholder="Pick an account"
                                    value={mapping[m] ?? null}
                                    onChange={(v) => setMapping((prev) => ({ ...prev, [m]: v }))}
                                    data={accountOptions}
                                />
                            ))}
                            {preview.budgetConflicts > 0 && (
                                <Radio.Group
                                    label={`${preview.budgetConflicts} budget cells already exist`}
                                    value={budgetPolicy}
                                    onChange={setBudgetPolicy}
                                >
                                    <div style={{ display: "flex", gap: 16, paddingTop: 6 }}>
                                        <Radio value="overwrite" label="Overwrite" />
                                        <Radio value="skip" label="Keep mine" />
                                    </div>
                                </Radio.Group>
                            )}
                        </>
                    )}
                    {result && (
                        <Txt>
                            Imported {result.inserted} transactions ({result.skipped} duplicates
                            skipped), {result.groupsCreated} groups and {result.categoriesCreated}{" "}
                            categories created, {result.budgetsWritten} budget cells written.
                        </Txt>
                    )}
                </div>
                <div className="migrate-panel__footer">
                    <Button size="l" variant="subtle" onClick={onClose}>
                        {result ? "Close" : "Cancel"}
                    </Button>
                    <Button
                        size="l"
                        variant="filled"
                        loading={busy && !!preview}
                        disabled={!result && (!preview || !allMapped)}
                        onClick={result ? onClose : commit}
                    >
                        {result ? "Done" : "Import"}
                    </Button>
                </div>
            </div>
        </aside>
    );
}
