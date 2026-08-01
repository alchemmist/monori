import { useEffect } from "react";
import { useStore } from "../store.js";
import { AccountEditTab } from "./AccountDialogs.jsx";
import AddTxTab from "./AddTxTab.jsx";
import AdminSqlTab from "./AdminSqlTab.jsx";
import AdminTxTab from "./AdminTxTab.jsx";
import MigratePanel from "./MigratePanel.jsx";
import ImportPanel from "./ImportPanel.jsx";
import SplitTransactionTab from "./SplitTransactionTab.jsx";
import type { Id, User } from "../types.js";

const isUser = (value: unknown): value is User =>
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "number" &&
    "email" in value &&
    typeof value.email === "string";

/**
 * Renders the store's global tab stack at the app-shell level, so open tabs
 * survive any in-app navigation — and, since the stack is persisted, a page
 * reload too. A tab only goes away when the user closes it (or its subject
 * disappears, e.g. the edited account got deleted).
 */

/** Drops a restored tab whose kind this build no longer knows about. */
function UnknownTab({ onClose }: { onClose: () => void }) {
    useEffect(() => {
        onClose();
    }, [onClose]);
    return null;
}

function AccountEditHost({ accountId, onClose }: { accountId?: Id; onClose: () => void }) {
    const account = useStore((s) =>
        accountId != null ? (s.snapshot?.accounts ?? []).find((a) => a.id === accountId) : null,
    );
    const missing = accountId != null && account == null;
    useEffect(() => {
        if (missing) onClose();
    }, [missing, onClose]);
    if (missing) return null;
    return <AccountEditTab account={account ?? {}} onClose={onClose} />;
}

function TransactionSplitHost({
    transactionId,
    onClose,
}: {
    transactionId?: Id;
    onClose: () => void;
}) {
    const transaction = useStore((s) =>
        transactionId != null
            ? (s.snapshot?.transactions ?? []).find((candidate) => candidate.id === transactionId)
            : null,
    );
    const missing = transactionId != null && transaction == null;
    useEffect(() => {
        if (missing) onClose();
    }, [missing, onClose]);
    if (missing) return null;
    return (
        <SplitTransactionTab
            {...(transaction === undefined ? {} : { transaction })}
            onClose={onClose}
        />
    );
}

export default function TabHost() {
    const tabs = useStore((s) => s.tabs);
    const closeTab = useStore((s) => s.closeTab);
    return tabs.map((t) => {
        const close = () => closeTab(t.id);
        if (t.kind === "account-edit") {
            const accountId =
                typeof t.props["accountId"] === "number" ? t.props["accountId"] : undefined;
            return (
                <AccountEditHost
                    key={t.id}
                    {...(accountId === undefined ? {} : { accountId })}
                    onClose={close}
                />
            );
        }
        if (t.kind === "tx-new") {
            return <AddTxTab key={t.id} onClose={close} />;
        }
        if (t.kind === "tx-split") {
            const transactionId =
                typeof t.props["transactionId"] === "number" ? t.props["transactionId"] : undefined;
            return (
                <TransactionSplitHost
                    key={t.id}
                    {...(transactionId === undefined ? {} : { transactionId })}
                    onClose={close}
                />
            );
        }
        if (t.kind === "admin-tx") {
            const user = t.props["user"];
            if (!isUser(user)) return <UnknownTab key={t.id} onClose={close} />;
            return <AdminTxTab key={t.id} user={user} onClose={close} />;
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
