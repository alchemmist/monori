import { useRef, useState } from "react";
import { Button, Checkbox, Radio } from "@mantine/core";
import { useStore } from "../store.js";
import { api } from "../api.js";
import { FSelect } from "../ui/fields.jsx";
import Tab from "../ui/Tab.jsx";
import Txt from "../ui/Txt.jsx";

/* A Tab instead of a modal so the app stays usable mid-migration:
 * collapse it to a strip, create the missing accounts, expand and finish —
 * the chosen file and preview survive the whole time. */
export default function MigratePanel({ onClose }) {
    const accounts = useStore((s) => s.snapshot?.accounts ?? []);
    const load = useStore((s) => s.load);
    const notify = useStore((s) => s.notify);
    const fileRef = useRef(null);
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [mapping, setMapping] = useState({});
    const [budgetPolicy, setBudgetPolicy] = useState("overwrite");
    const [remember, setRemember] = useState(true);
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);

    const live = accounts.filter((a) => !a.archived);
    const optionsIn = (currency) =>
        live
            .filter((a) => (a.currency || "RUB").toUpperCase() === currency)
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

    const slots = preview?.accountSlots ?? [];
    const allMapped = slots.every((s) => mapping[s.key]);

    const commit = async () => {
        setBusy(true);
        try {
            const numeric = Object.fromEntries(slots.map((s) => [s.key, Number(mapping[s.key])]));
            const r = await api.workbookCommit(file, numeric, budgetPolicy, remember);
            setResult(r);
            await load();
        } catch (e) {
            notify({ title: "Migration failed", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    const footer = (
        <>
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
        </>
    );

    return (
        <Tab title="Migrate from spreadsheet" strip="Migration" onClose={onClose} footer={footer}>
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
                    {slots.length > 0 && (
                        <Txt tone="secondary" caption>
                            Missing an account? Collapse this tab with the arrow above, create it,
                            then come back — the file stays loaded.
                        </Txt>
                    )}
                    {slots.map((s) => {
                        const data = optionsIn(s.currency);
                        const who = s.marker || "unmarked rows";
                        return (
                            <div key={s.key}>
                                <FSelect
                                    label={
                                        s.currency === "RUB"
                                            ? `Account for ${who}`
                                            : `Account for ${who} · ${s.currency} (${s.transactions} rows)`
                                    }
                                    placeholder={
                                        data.length
                                            ? "Pick an account"
                                            : `No ${s.currency} account yet — create one`
                                    }
                                    value={mapping[s.key] ?? null}
                                    onChange={(v) =>
                                        setMapping((prev) => ({ ...prev, [s.key]: v }))
                                    }
                                    data={data}
                                />
                                {data.length === 0 && (
                                    <Txt tone="danger" caption>
                                        These rows are in {s.currency}. Create an account held in{" "}
                                        {s.currency} to import them — on an account in another
                                        currency the amounts would be recorded at face value.
                                    </Txt>
                                )}
                            </div>
                        );
                    })}
                    {slots.some((s) => /\d/.test(s.marker)) && (
                        <Checkbox
                            label="Remember which card belongs to which account"
                            description="The card numbers above are saved on their accounts, so future imports and bank syncs route them automatically"
                            checked={remember}
                            onChange={(e) => setRemember(e.currentTarget.checked)}
                        />
                    )}
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
                    Imported {result.inserted} transactions ({result.skipped} duplicates skipped),{" "}
                    {result.groupsCreated} groups and {result.categoriesCreated} categories created,{" "}
                    {result.budgetsWritten} budget cells written.
                    {result.cardTailsBound > 0 &&
                        ` ${result.cardTailsBound} card numbers remembered on their accounts.`}
                </Txt>
            )}
        </Tab>
    );
}
