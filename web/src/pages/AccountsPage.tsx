import {
    useEffect,
    useMemo,
    useRef,
    useState,
    type CSSProperties,
    type PointerEvent as ReactPointerEvent,
} from "react";
import RowMenu from "../ui/RowMenu.jsx";
import Tag from "../ui/Tag.jsx";
import { Plus, Grip } from "@gravity-ui/icons";
import { useStore, isDemo } from "../store.js";
import { api } from "../api.js";
import { accountBalances } from "../engine/analytics.js";
import AccountBadge from "../components/AccountBadge.jsx";
import { money } from "../format.js";
import { AccountDeleteDialog, AccountReconcileDialog } from "../components/AccountDialogs.jsx";
import ConnectionDialog from "../components/ConnectionDialog.jsx";
import "./accounts.css";
import type { Account, Connection, Id } from "../types.js";

const TYPE_LABEL: Record<string, string> = {
    card: "Card",
    cash: "Cash",
    savings: "Savings",
    other: "Other",
};

type AccountDialog = { type: "delete" | "reconcile" | "connection"; account: Account };
interface AccountDrag {
    fromIndex: number;
    targetIndex: number;
    startY: number;
    dy: number;
    rowH: number;
}

export default function AccountsPage() {
    const { snapshot, notify, openTab } = useStore();
    if (!snapshot) throw new Error("accounts page requires a loaded snapshot");
    const [dialog, setDialog] = useState<AccountDialog | null>(null);

    const accounts = snapshot.accounts;
    const connByAccount = useMemo(() => {
        const connections = snapshot.connections === undefined ? [] : snapshot.connections;
        const byId = new Map(connections.map((c) => [c.id, c]));
        const m = new Map<Id, Connection>();
        for (const a of snapshot.accounts) {
            const conn = a.connectionId != null ? byId.get(a.connectionId) : null;
            if (conn != null) m.set(a.id, conn);
        }
        return m;
    }, [snapshot.connections, snapshot.accounts]);
    const balances = useMemo(() => accountBalances(snapshot), [snapshot]);
    const txCounts = useMemo(() => {
        const m = new Map<Id, number>();
        for (const t of snapshot.transactions) m.set(t.accountId, (m.get(t.accountId) ?? 0) + 1);
        return m;
    }, [snapshot.transactions]);

    const commitOrder = (ids: Id[]) => {
        const reordered = ids
            .map((id) => accounts.find((account) => account.id === id))
            .filter((account): account is Account => account !== undefined);
        useStore.setState({ snapshot: { ...snapshot, accounts: reordered } });
        if (isDemo()) return;
        api.reorderAccounts(ids).catch((e) =>
            notify({ title: "Failed to reorder", theme: "danger", content: String(e) }),
        );
    };

    const [drag, setDrag] = useState<AccountDrag | null>(null);
    const dragRef = useRef<AccountDrag | null>(null);
    const accountsRef = useRef(accounts);
    accountsRef.current = accounts;
    const commitRef = useRef(commitOrder);
    commitRef.current = commitOrder;
    const dragging = drag !== null;

    const startDrag = (e: ReactPointerEvent<HTMLButtonElement>, fromIndex: number) => {
        if (e.button !== 0) return;
        e.preventDefault();
        const row = e.currentTarget.closest<HTMLElement>(".account-row");
        if (!row) return;
        const rowH = row.getBoundingClientRect().height;
        const st = { fromIndex, targetIndex: fromIndex, startY: e.clientY, dy: 0, rowH };
        dragRef.current = st;
        setDrag(st);
        document.body.style.userSelect = "none";
    };

    useEffect(() => {
        if (!dragging) return;
        const onMove = (e: PointerEvent) => {
            const st = dragRef.current;
            if (!st) return;
            const dy = e.clientY - st.startY;
            const n = accountsRef.current.length;
            const targetIndex = Math.max(
                0,
                Math.min(n - 1, st.fromIndex + Math.round(dy / st.rowH)),
            );
            dragRef.current = { ...st, dy, targetIndex };
            setDrag(dragRef.current);
        };
        const onUp = () => {
            const st = dragRef.current;
            document.body.style.userSelect = "";
            dragRef.current = null;
            setDrag(null);
            if (!st) return;
            if (st.targetIndex !== st.fromIndex) {
                const ids = accountsRef.current.map((a) => a.id);
                const [moved] = ids.splice(st.fromIndex, 1);
                if (moved !== undefined) ids.splice(st.targetIndex, 0, moved);
                commitRef.current(ids);
            }
        };
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
        return () => {
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
        };
    }, [dragging]);

    const rowStyle = (i: number): CSSProperties | undefined => {
        if (!drag) return undefined;
        const { fromIndex, targetIndex, dy, rowH } = drag;
        if (i === fromIndex) {
            const n = accounts.length;
            const clamped = Math.max(-fromIndex * rowH, Math.min((n - 1 - fromIndex) * rowH, dy));
            return { transform: `translateY(${clamped}px)`, transition: "none", zIndex: 2 };
        }
        let shift = 0;
        if (fromIndex < targetIndex && i > fromIndex && i <= targetIndex) shift = -1;
        else if (fromIndex > targetIndex && i >= targetIndex && i < fromIndex) shift = 1;
        return {
            transform: `translateY(${shift * rowH}px)`,
            transition: "transform 0.18s cubic-bezier(0.2, 0, 0, 1)",
        };
    };

    return (
        <div className="fade-in">
            <div className="budget-toolbar">
                <h1 className="page-title" style={{ margin: 0 }}>
                    Accounts
                </h1>
            </div>

            <div className="card account-list">
                {accounts.map((a, i) => {
                    const isDragged = drag?.fromIndex === i;
                    const connection = connByAccount.get(a.id);
                    return (
                        <div
                            key={a.id}
                            className={`account-row account-row_draggable${isDragged ? " account-row_dragging" : ""}`}
                            style={rowStyle(i)}
                        >
                            <button
                                type="button"
                                className="account-row__grip"
                                onPointerDown={(e) => startDrag(e, i)}
                                aria-label="Drag to reorder"
                            >
                                <Grip width={16} height={16} />
                            </button>
                            <AccountBadge account={a} size={32} />
                            <div className="account-row__main">
                                <span className="account-row__name">{a.name}</span>
                                <Tag theme="unknown">{TYPE_LABEL[a.type] ?? a.type}</Tag>
                                {a.archived && <Tag theme="warning">archived</Tag>}
                                {connection && (
                                    <Tag
                                        theme={
                                            connection.status === "error"
                                                ? "danger"
                                                : connection.status === "connected"
                                                  ? "success"
                                                  : "info"
                                        }
                                    >
                                        {connection.status === "connected"
                                            ? "synced"
                                            : connection.status}
                                    </Tag>
                                )}
                            </div>
                            <span className="account-row__balance num">
                                {money(balances.get(a.id) ?? 0)}
                            </span>
                            <div className="account-row__actions">
                                <RowMenu
                                    size="s"
                                    items={[
                                        {
                                            text: "Edit",
                                            action: () =>
                                                openTab(
                                                    "account-edit",
                                                    { accountId: a.id },
                                                    `account-edit:${a.id}`,
                                                ),
                                        },
                                        {
                                            text: "Reconcile",
                                            action: () =>
                                                setDialog({ type: "reconcile", account: a }),
                                        },
                                        {
                                            text: connByAccount.has(a.id)
                                                ? "Bank sync"
                                                : "Connect bank",
                                            action: () =>
                                                setDialog({ type: "connection", account: a }),
                                        },
                                        {
                                            text: a.archived ? "Unarchive" : "Archive",
                                            action: () =>
                                                void useStore
                                                    .getState()
                                                    .patchAccount(a.id, { archived: !a.archived })
                                                    .catch((e) =>
                                                        notify({
                                                            title: "Failed to update account",
                                                            theme: "danger",
                                                            content: String(e),
                                                        }),
                                                    ),
                                        },
                                        {
                                            text: "Delete",
                                            theme: "danger",
                                            action: () => setDialog({ type: "delete", account: a }),
                                        },
                                    ]}
                                />
                            </div>
                        </div>
                    );
                })}
                <button
                    type="button"
                    className="account-row account-row_add"
                    onClick={() => openTab("account-edit", {}, "account-new")}
                >
                    <Plus width={16} height={16} />
                    <span>New account</span>
                </button>
            </div>

            {dialog?.type === "delete" && (
                <AccountDeleteDialog
                    account={dialog.account}
                    accounts={accounts}
                    txCount={txCounts.get(dialog.account.id) ?? 0}
                    onClose={() => setDialog(null)}
                />
            )}
            {dialog?.type === "reconcile" && (
                <AccountReconcileDialog
                    account={dialog.account}
                    balance={balances.get(dialog.account.id) ?? 0}
                    onClose={() => setDialog(null)}
                />
            )}
            {dialog?.type === "connection" && (
                <ConnectionDialog
                    account={dialog.account}
                    connection={connByAccount.get(dialog.account.id) ?? null}
                    onClose={() => setDialog(null)}
                />
            )}
        </div>
    );
}
