import { SegmentedControl } from "@mantine/core";

export default function SettingsPage({ theme, onToggleTheme }) {
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
        </div>
    );
}
