import { Button, SegmentedControl } from "@mantine/core";
import { useState } from "react";

import { api } from "../api.js";

export default function SettingsPage({ theme, onToggleTheme }) {
    const [exporting, setExporting] = useState(false);

    const exportXlsx = async () => {
        setExporting(true);
        try {
            const blob = await api.exportXlsx();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "monori-export.xlsx";
            a.click();
            URL.revokeObjectURL(url);
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
                        Download all data as a YNAB-style Excel workbook
                    </div>
                </div>
                <Button variant="default" loading={exporting} onClick={exportXlsx}>
                    Export to Excel
                </Button>
            </div>
        </div>
    );
}
