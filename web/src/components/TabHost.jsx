import { useEffect } from "react";
import { useStore } from "../store.js";
import { AccountEditTab } from "./AccountDialogs.jsx";
import AddTxTab from "./AddTxTab.jsx";
import AdminSqlTab from "./AdminSqlTab.jsx";
import AdminTxTab from "./AdminTxTab.jsx";
import MigratePanel from "./MigratePanel.jsx";
import ImportPanel from "./ImportPanel.jsx";

/**
 * Renders the store's global tab stack at the app-shell level, so open tabs
 * survive any in-app navigation — and, since the stack is persisted, a page
 * reload too. A tab only goes away when the user closes it (or its subject
 * disappears, e.g. the edited account got deleted).
 */

/** Drops a restored tab whose kind this build no longer knows about. */
function UnknownTab({ onClose }) {
    useEffect(() => {
        onClose();
    }, [onClose]);
    return null;
}

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
        if (t.kind === "tx-new") {
            return <AddTxTab key={t.id} onClose={close} />;
        }
        if (t.kind === "admin-tx") {
            return <AdminTxTab key={t.id} user={t.props.user} onClose={close} />;
        }
        if (t.kind === "admin-sql") {
            return <AdminSqlTab key={t.id} onClose={close} />;
        }
        if (t.kind === "migrate") {
            return <MigratePanel key={t.id} onClose={close} />;
        }
        if (t.kind === "statement-import") {
            return <ImportPanel key={t.id} onClose={close} />;
        }
        return <UnknownTab key={t.id} onClose={close} />;
    });
}
