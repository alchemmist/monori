import { Button, SegmentedControl } from "@mantine/core";
import { useState } from "react";

import { api } from "../api.js";
import { seedDemoData } from "../demo/seedDemo.js";
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
    const [exporting, setExporting] = useState(false);
    const [exportError, setExportError] = useState("");
    const [seedingDemo, setSeedingDemo] = useState(false);

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
