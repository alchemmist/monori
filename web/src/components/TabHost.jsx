import { useEffect } from "react";
import { useStore } from "../store.js";
import { AccountEditTab } from "./AccountDialogs.jsx";
import AdminTxTab from "./AdminTxTab.jsx";
import MigratePanel from "./MigratePanel.jsx";

/**
 * Renders the store's global tab stack at the app-shell level, so open tabs
 * survive any in-app navigation — a tab only goes away when the user closes
 * it (or its subject disappears, e.g. the edited account got deleted).
 */

function AccountEditHost({ accountId, onClose }) {
    const account = useStore((s) =>
        accountId ? (s.snapshot?.accounts ?? []).find((a) => a.id === accountId) : null,
    );
    const missing = accountId != null && !account;
    useEffect(() => {
        if (missing) onClose();
    }, [missing, onClose]);
    if (missing) return null;
    return <AccountEditTab account={account ?? {}} onClose={onClose} />;
}

export default function TabHost() {
    const tabs = useStore((s) => s.tabs);
    const closeTab = useStore((s) => s.closeTab);
    return tabs.map((t) => {
        const close = () => closeTab(t.id);
        if (t.kind === "account-edit") {
            return <AccountEditHost key={t.id} accountId={t.props.accountId} onClose={close} />;
        }
        if (t.kind === "admin-tx") {
            return (
                <AdminTxTab
                    key={t.id}
                    user={t.props.user}
                    onChanged={t.props.onChanged}
                    onClose={close}
                />
            );
        }
        if (t.kind === "migrate") {
            return <MigratePanel key={t.id} onClose={close} />;
        }
        return null;
    });
}
