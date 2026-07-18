import { SegmentedRadioGroup } from "@gravity-ui/uikit";

export default function SettingsPage({ theme, onToggleTheme }) {
    return (
        <div className="fade-in">
            <h1 className="page-title">Settings</h1>
            <div className="card settings-row">
                <div className="settings-row__text">
                    <div className="settings-row__title">Theme</div>
                    <div className="settings-row__hint">Light or dark appearance</div>
                </div>
                <SegmentedRadioGroup
                    size="l"
                    value={theme}
                    onUpdate={(v) => {
                        if (v !== theme) onToggleTheme();
                    }}
                    options={[
                        { value: "light", content: "Light" },
                        { value: "dark", content: "Dark" },
                    ]}
                />
            </div>
        </div>
    );
}
