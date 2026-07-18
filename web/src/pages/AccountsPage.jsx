import { useEffect, useMemo, useRef, useState } from "react";
import { Button, DropdownMenu, Label } from "@gravity-ui/uikit";
import { Plus, Grip } from "@gravity-ui/icons";
import { useStore, isDemo } from "../store.js";
import { api } from "../api.js";
import { accountBalances } from "../engine/analytics.js";
import AccountBadge from "../components/AccountBadge.jsx";
import { money } from "../format.js";
import {
  AccountEditDialog,
  AccountDeleteDialog,
  AccountReconcileDialog,
} from "../components/AccountDialogs.jsx";
import "./accounts.css";

const TYPE_LABEL = { card: "Card", cash: "Cash", savings: "Savings", other: "Other" };

export default function AccountsPage() {
  const { snapshot, notify } = useStore();
  const [dialog, setDialog] = useState(null);

  const accounts = snapshot.accounts ?? [];
  const balances = useMemo(() => accountBalances(snapshot), [snapshot]);
  const txCounts = useMemo(() => {
    const m = new Map();
    for (const t of snapshot.transactions) m.set(t.accountId, (m.get(t.accountId) ?? 0) + 1);
    return m;
  }, [snapshot.transactions]);

  const commitOrder = (ids) => {
    const reordered = ids.map((x) => accounts.find((a) => a.id === x));
    useStore.setState({ snapshot: { ...snapshot, accounts: reordered } });
    if (isDemo()) return;
    api
      .reorderAccounts(ids)
      .catch((e) => notify({ title: "Failed to reorder", theme: "danger", content: String(e) }));
  };

  const [drag, setDrag] = useState(null);
  const dragRef = useRef(null);
  const accountsRef = useRef(accounts);
  accountsRef.current = accounts;
  const commitRef = useRef(commitOrder);
  commitRef.current = commitOrder;
  const dragging = drag !== null;

  const startDrag = (e, fromIndex) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const rowH = e.currentTarget.closest(".account-row").getBoundingClientRect().height;
    const st = { fromIndex, targetIndex: fromIndex, startY: e.clientY, dy: 0, rowH };
    dragRef.current = st;
    setDrag(st);
    document.body.style.userSelect = "none";
  };

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e) => {
      const st = dragRef.current;
      const dy = e.clientY - st.startY;
      const n = accountsRef.current.length;
      const targetIndex = Math.max(0, Math.min(n - 1, st.fromIndex + Math.round(dy / st.rowH)));
      dragRef.current = { ...st, dy, targetIndex };
      setDrag(dragRef.current);
    };
    const onUp = () => {
      const st = dragRef.current;
      document.body.style.userSelect = "";
      dragRef.current = null;
      setDrag(null);
      if (st.targetIndex !== st.fromIndex) {
        const ids = accountsRef.current.map((a) => a.id);
        const [moved] = ids.splice(st.fromIndex, 1);
        ids.splice(st.targetIndex, 0, moved);
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

  const rowStyle = (i) => {
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
        <div style={{ flex: 1 }} />
        <Button view="action" size="m" onClick={() => setDialog({ type: "edit", account: {} })}>
          <Plus width={14} height={14} /> New account
        </Button>
      </div>

      <div className="card account-list">
        {accounts.map((a, i) => {
          const isDragged = drag?.fromIndex === i;
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
                <Label size="xs" theme="unknown">
                  {TYPE_LABEL[a.type] ?? a.type}
                </Label>
                {a.archived && (
                  <Label size="xs" theme="warning">
                    archived
                  </Label>
                )}
              </div>
              <span className="account-row__balance num">{money(balances.get(a.id) ?? 0)}</span>
              <div className="account-row__actions">
                <DropdownMenu
                  size="s"
                  items={[
                    { text: "Edit", action: () => setDialog({ type: "edit", account: a }) },
                    {
                      text: "Reconcile",
                      action: () => setDialog({ type: "reconcile", account: a }),
                    },
                    {
                      text: a.archived ? "Unarchive" : "Archive",
                      action: () =>
                        useStore
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
      </div>

      {dialog?.type === "edit" && (
        <AccountEditDialog account={dialog.account} onClose={() => setDialog(null)} />
      )}
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
    </div>
  );
}
