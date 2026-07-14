import { useMemo, useState } from "react";
import { Button, DropdownMenu, Label, SegmentedRadioGroup } from "@gravity-ui/uikit";
import { Plus, ArrowUp, ArrowDown } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { api } from "../api.js";
import { isDemo } from "../store.js";
import { accountBalances } from "../engine/analytics.js";
import { money } from "../format.js";
import {
  AccountEditDialog,
  AccountDeleteDialog,
  AccountReconcileDialog,
} from "../components/AccountDialogs.jsx";
import "./settings.css";

const TYPE_LABEL = { card: "Card", cash: "Cash", savings: "Savings", other: "Other" };

export default function SettingsPage({ theme, onToggleTheme }) {
  const { snapshot, notify } = useStore();
  const [dialog, setDialog] = useState(null);

  const accounts = snapshot.accounts ?? [];
  const balances = useMemo(() => accountBalances(snapshot), [snapshot]);
  const txCounts = useMemo(() => {
    const m = new Map();
    for (const t of snapshot.transactions) m.set(t.accountId, (m.get(t.accountId) ?? 0) + 1);
    return m;
  }, [snapshot.transactions]);

  const reorder = async (id, dir) => {
    const ids = accounts.map((a) => a.id);
    const i = ids.indexOf(id);
    const j = i + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    const reordered = ids.map((x) => accounts.find((a) => a.id === x));
    useStore.setState({ snapshot: { ...snapshot, accounts: reordered } });
    if (isDemo()) return;
    api
      .reorderAccounts(ids)
      .catch((e) => notify({ title: "Failed to reorder", theme: "danger", content: String(e) }));
  };

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

      <div className="settings-section">
        <div className="settings-section__head">
          <div>
            <div className="settings-row__title">Accounts</div>
            <div className="settings-row__hint">
              Cards, cash and savings. Every transaction belongs to an account.
            </div>
          </div>
          <Button view="action" size="m" onClick={() => setDialog({ type: "edit", account: {} })}>
            <Plus width={14} height={14} /> New account
          </Button>
        </div>

        <div className="card account-list">
          {accounts.map((a, i) => (
            <div key={a.id} className="account-row">
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
                <Button
                  view="flat"
                  size="s"
                  disabled={i === 0}
                  onClick={() => reorder(a.id, -1)}
                  aria-label="Move up"
                >
                  <ArrowUp width={14} height={14} />
                </Button>
                <Button
                  view="flat"
                  size="s"
                  disabled={i === accounts.length - 1}
                  onClick={() => reorder(a.id, 1)}
                  aria-label="Move down"
                >
                  <ArrowDown width={14} height={14} />
                </Button>
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
                        useStore.getState().patchAccount(a.id, { archived: !a.archived }),
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
          ))}
        </div>
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
