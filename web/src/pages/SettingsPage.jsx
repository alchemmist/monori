import { Button, SegmentedControl } from "@mantine/core";
import { useState } from "react";

import { FSelect } from "../ui/fields.jsx";

import { api } from "../api.js";
import RatesPanel from "../components/RatesPanel.jsx";
import { DEFAULT_CURRENCY, currencyOptions } from "../currencies.js";
import { seedDemoData } from "../demo/seedDemo.js";
import InlineSelect from "../ui/InlineSelect.jsx";
import { isDemo, useStore } from "../store.js";
import { fmtDate } from "../format.js";
import "./settings.css";

function Section({ title, children }) {
    return (
        <section>
            <h2 className="settings__section-title">{title}</h2>
            <div className="card settings__group">{children}</div>
        </section>
    );
}

function Row({ label, hint, hintBad, children }) {
    return (
        <div className="settings__row">
            <div>
                <div className="settings__label">{label}</div>
                {hint && (
                    <div className={`settings__hint${hintBad ? " settings__hint_bad" : ""}`}>
                        {hint}
                    </div>
                )}
            </div>
            {children}
        </div>
    );
}

export default function SettingsPage({ theme, onToggleTheme, onMigrate }) {
    const user = useStore((s) => s.user);
    const logout = useStore((s) => s.logout);
    const snapshot = useStore((s) => s.snapshot);
    const load = useStore((s) => s.load);
    const notify = useStore((s) => s.notify);
    const patchMe = useStore((s) => s.patchMe);
    const [exporting, setExporting] = useState(false);
    const [exportError, setExportError] = useState("");
    const [seedingDemo, setSeedingDemo] = useState(false);
    const setBaseCurrency = useStore((s) => s.setBaseCurrency);
    const [repricing, setRepricing] = useState(false);
    const base = snapshot?.baseCurrency ?? user?.baseCurrency ?? DEFAULT_CURRENCY;

    const changeBase = async (code) => {
        if (!code || code === base) return;
        setRepricing(true);
        try {
            await setBaseCurrency(code);
            notify({ title: `Now reporting in ${code}`, theme: "success" });
        } catch (e) {
            notify({
                title: "Could not change the reporting currency",
                theme: "danger",
                content: String(e),
            });
        } finally {
            setRepricing(false);
        }
    };

    const exportXlsx = async () => {
        setExporting(true);
        setExportError("");
        try {
            const blob = await api.exportXlsx();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "monori-export.xlsx";
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 10000);
        } catch (e) {
            setExportError(e.message || "Export failed");
        } finally {
            setExporting(false);
        }
    };

    const loadDemoData = async () => {
        if (!snapshot) return;
        setSeedingDemo(true);
        try {
            const { imported, skipped, transfers } = await seedDemoData();
            await load();
            const added = imported + transfers;
            notify({
                title: added ? "Demo data added" : "Demo data is already loaded",
                theme: "success",
                content: added
                    ? `${imported} transactions and ${transfers} transfers added${
                          skipped ? `; ${skipped} duplicates skipped` : ""
                      }.`
                    : undefined,
            });
        } catch (e) {
            await load();
            notify({ title: "Could not add demo data", theme: "danger", content: String(e) });
        } finally {
            setSeedingDemo(false);
        }
    };

    return (
        <div className="fade-in">
            <h1 className="page-title">Settings</h1>
            <div className="settings">
                {!isDemo() && user && (
                    <Section title="Account">
                        <div className="settings__identity">
                            <div className="settings__avatar" aria-hidden="true">
                                {user.email.slice(0, 1)}
                            </div>
                            <div>
                                <div className="settings__email">{user.email}</div>
                                <div className="settings__meta">
                                    {user.createdAt && (
                                        <span>Joined {fmtDate(user.createdAt)}</span>
                                    )}
                                    {user.isAdmin && <span className="settings__badge">Admin</span>}
                                </div>
                            </div>
                        </div>
                        <Row label="Session" hint="End this session on this device">
                            <Button variant="outline" data-tone="danger" onClick={logout}>
                                Log out
                            </Button>
                        </Row>
                    </Section>
                )}

                <Section title="Currency">
                    <Row
                        label="Reporting currency"
                        hint={
                            repricing
                                ? "Repricing the ledger…"
                                : "What every total is expressed in. Each transaction keeps the" +
                                  " currency it was recorded in; changing this only changes what" +
                                  " they are added up as."
                        }
                    >
                        <InlineSelect
                            value={base}
                            onChange={changeBase}
                            data={currencyOptions(base)}
                            disabled={repricing}
                        />
                    </Row>
                    <RatesPanel />
                </Section>

                <Section title="Appearance">
                    <Row label="Theme" hint="Light or dark appearance">
                        <SegmentedControl
                            className="seg-l"
                            value={theme}
                            onChange={(v) => {
                                if (v !== theme) onToggleTheme();
                            }}
                            data={[
                                { value: "light", label: "Light" },
                                { value: "dark", label: "Dark" },
                            ]}
                        />
                    </Row>
                </Section>

                {!isDemo() && user && (
                    <Section title="Imports">
                        <Row
                            label="Default account"
                            hint="Where imports put transactions whose card number is missing — leave empty to assign them by hand"
                        >
                            <FSelect
                                className="settings__control"
                                placeholder="No default"
                                value={
                                    user.defaultAccountId != null
                                        ? String(user.defaultAccountId)
                                        : ""
                                }
                                onChange={(v) =>
                                    patchMe({ defaultAccountId: v ? Number(v) : null }).catch((e) =>
                                        notify({
                                            title: "Could not save the default account",
                                            theme: "danger",
                                            content: String(e),
                                        }),
                                    )
                                }
                                data={[
                                    { value: "", label: "No default" },
                                    ...(snapshot?.accounts ?? [])
                                        .filter((a) => !a.archived)
                                        .map((a) => ({ value: String(a.id), label: a.name })),
                                ]}
                            />
                        </Row>
                    </Section>
                )}

                <Section title="Data">
                    <Row
                        label="Export"
                        hint={exportError || "Download all data as a YNAB-style Excel workbook"}
                        hintBad={!!exportError}
                    >
                        <Button variant="default" loading={exporting} onClick={exportXlsx}>
                            Export to Excel
                        </Button>
                    </Row>
                    <Row
                        label="Migrate"
                        hint="Import categories, transactions and budgets from a YNAB-style workbook"
                    >
                        <Button variant="default" onClick={onMigrate}>
                            Migrate from spreadsheet
                        </Button>
                    </Row>
                    {!isDemo() && (
                        <Row
                            label="Demo data"
                            hint="Add the sample accounts, categories, budgets and transactions from the demo"
                        >
                            <Button
                                variant="default"
                                loading={seedingDemo}
                                disabled={!snapshot}
                                onClick={loadDemoData}
                            >
                                Add demo data
                            </Button>
                        </Row>
                    )}
                </Section>
            </div>
        </div>
    );
}
