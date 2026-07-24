import { Button, SegmentedControl } from "@mantine/core";
import { useState } from "react";

import { api } from "../api.js";
import MigrateDialog from "../components/MigrateDialog.jsx";

export default function SettingsPage({ theme, onToggleTheme }) {
    const [exporting, setExporting] = useState(false);
    const [exportError, setExportError] = useState("");
    const [migrating, setMigrating] = useState(false);

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

    return (
        <div className="fade-in">
            <h1 className="page-title">Settings</h1>
            <div className="card settings-row">
                <div className="settings-row__text">
                    <div className="settings-row__title">Theme</div>
                    <div className="settings-row__hint">Light or dark appearance</div>
                </div>
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
            </div>
            <div className="card settings-row">
                <div className="settings-row__text">
                    <div className="settings-row__title">Export</div>
                    <div className="settings-row__hint">
                        {exportError || "Download all data as a YNAB-style Excel workbook"}
                    </div>
                </div>
                <Button variant="default" loading={exporting} onClick={exportXlsx}>
                    Export to Excel
                </Button>
            </div>
            <div className="card settings-row">
                <div className="settings-row__text">
                    <div className="settings-row__title">Migrate</div>
                    <div className="settings-row__hint">
                        Import categories, transactions and budgets from a YNAB-style workbook
                    </div>
                </div>
                <Button variant="default" onClick={() => setMigrating(true)}>
                    Migrate from spreadsheet
                </Button>
            </div>
            {migrating && <MigrateDialog onClose={() => setMigrating(false)} />}
        </div>
    );
}
