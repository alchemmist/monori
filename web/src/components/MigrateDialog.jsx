import { useRef, useState } from "react";
import { Button, Radio } from "@mantine/core";
import { useStore } from "../store.js";
import { api } from "../api.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FSelect } from "../ui/fields.jsx";
import Txt from "../ui/Txt.jsx";

export default function MigrateDialog({ onClose }) {
    const accounts = useStore((s) => s.snapshot?.accounts ?? []);
    const load = useStore((s) => s.load);
    const notify = useStore((s) => s.notify);
    const fileRef = useRef(null);
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

    return (
        <AppDialog
            title="Migrate from spreadsheet"
            onClose={onClose}
            applyText={result ? "Done" : "Import"}
            onApply={result ? onClose : commit}
            applyLoading={busy}
            applyDisabled={!result && (!preview || !allMapped)}
            cancelText={result ? "Close" : "Cancel"}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <input
                    ref={fileRef}
                    type="file"
                    accept=".xlsx"
                    style={{ display: "none" }}
                    onChange={(e) => pick(e.target.files?.[0])}
                />
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <Button variant="default" onClick={() => fileRef.current?.click()}>
                        {file ? "Choose another file" : "Choose .xlsx file"}
                    </Button>
                    {file && <Txt tone="secondary">{file.name}</Txt>}
                </div>
                {preview && !result && (
                    <>
                        <Txt>
                            {preview.groups} groups, {preview.categories} categories,{" "}
                            {preview.transactions} transactions, {preview.budgetCells} budget cells
                        </Txt>
                        {preview.errors.length > 0 && (
                            <Txt tone="secondary" caption>
                                {preview.errors.length} rows could not be parsed and will be skipped
                            </Txt>
                        )}
                        {preview.warnings.map((w) => (
                            <Txt key={w} tone="secondary" caption>
                                {w}
                            </Txt>
                        ))}
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
        </AppDialog>
    );
}
