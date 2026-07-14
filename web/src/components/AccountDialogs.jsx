import { useState } from "react";
import { Dialog, TextInput, Select, Text } from "@gravity-ui/uikit";
import { useStore } from "../store.js";
import { parseRub, money } from "../format.js";
import { ACCOUNT_ICONS } from "./accountIcons.js";

const ACCOUNT_TYPES = [
  { value: "card", content: "Card" },
  { value: "cash", content: "Cash" },
  { value: "savings", content: "Savings" },
  { value: "other", content: "Other" },
];

export function AccountEditDialog({ account, onClose }) {
  const { createAccount, patchAccount, notify } = useStore();
  const isNew = !account.id;
  const [name, setName] = useState(account.name ?? "");
  const [type, setType] = useState(account.type ?? "other");
  const [icon, setIcon] = useState(account.icon ?? "wallet");
  const [currency, setCurrency] = useState(account.currency ?? "RUB");
  const [opening, setOpening] = useState(
    account.openingBalance ? String(account.openingBalance / 100) : "",
  );
  const [busy, setBusy] = useState(false);

  const apply = async () => {
    if (!name.trim()) return;
    const openingBalance = parseRub(opening);
    if (openingBalance == null) {
      notify({ title: "Opening balance is not a number", theme: "danger" });
      return;
    }
    setBusy(true);
    try {
      const body = {
        name: name.trim(),
        type,
        icon,
        currency: currency.trim() || "RUB",
        openingBalance,
      };
      if (isNew) await createAccount(body);
      else await patchAccount(account.id, body);
      onClose();
    } catch (e) {
      notify({
        title: isNew ? "Failed to create account" : "Failed to update account",
        theme: "danger",
        content: String(e),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onClose={onClose} size="s">
      <Dialog.Header caption={isNew ? "New account" : `Edit ${account.name}`} />
      <Dialog.Body>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
          <TextInput label="Name" value={name} onUpdate={setName} autoFocus />
          <Select
            label="Type"
            value={[type]}
            onUpdate={(v) => setType(v[0])}
            options={ACCOUNT_TYPES}
            width="max"
          />
          <div>
            <Text color="secondary" variant="caption-2">
              Icon
            </Text>
            <div className="icon-picker">
              {ACCOUNT_ICONS.map(({ name: iconName, Icon }) => (
                <button
                  key={iconName}
                  type="button"
                  className={`icon-picker__item ${icon === iconName ? "icon-picker__item_active" : ""}`}
                  onClick={() => setIcon(iconName)}
                  aria-label={iconName}
                  aria-pressed={icon === iconName}
                >
                  <Icon width={18} height={18} />
                </button>
              ))}
            </div>
          </div>
          <TextInput label="Currency" value={currency} onUpdate={setCurrency} />
          <TextInput
            label="Opening balance"
            value={opening}
            onUpdate={setOpening}
            placeholder="0"
          />
          <Text color="secondary" variant="caption-2">
            The running balance is the opening balance plus every transaction on this account.
            Currency is a label for now — all amounts are treated as a single currency.
          </Text>
        </div>
      </Dialog.Body>
      <Dialog.Footer
        textButtonApply={isNew ? "Create" : "Save"}
        textButtonCancel="Cancel"
        onClickButtonApply={apply}
        onClickButtonCancel={onClose}
        propsButtonApply={{ loading: busy, disabled: !name.trim() }}
      />
    </Dialog>
  );
}

export function AccountDeleteDialog({ account, accounts, txCount, onClose }) {
  const { deleteAccount, notify } = useStore();
  const others = accounts.filter((a) => a.id !== account.id);
  const [target, setTarget] = useState(others[0] ? String(others[0].id) : "");
  const [busy, setBusy] = useState(false);

  const apply = async () => {
    if (txCount > 0 && !target) return;
    setBusy(true);
    try {
      await deleteAccount(account.id, target ? +target : undefined);
      onClose();
    } catch (e) {
      notify({ title: "Failed to delete account", theme: "danger", content: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onClose={onClose} size="s">
      <Dialog.Header caption={`Delete ${account.name}`} />
      <Dialog.Body>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
          <Text>
            {txCount > 0
              ? `${txCount} transactions belong to this account. Move them where?`
              : "No transactions belong to this account."}
          </Text>
          {txCount > 0 && (
            <Select
              label="Move to"
              value={target ? [target] : []}
              onUpdate={(v) => setTarget(v[0] ?? "")}
              options={others.map((a) => ({ value: String(a.id), content: a.name }))}
              width="max"
            />
          )}
        </div>
      </Dialog.Body>
      <Dialog.Footer
        textButtonApply="Delete"
        textButtonCancel="Cancel"
        onClickButtonApply={apply}
        onClickButtonCancel={onClose}
        propsButtonApply={{
          view: "outlined-danger",
          loading: busy,
          disabled: txCount > 0 && !target,
        }}
      />
    </Dialog>
  );
}

export function AccountReconcileDialog({ account, balance, onClose }) {
  const { reconcileAccount, notify } = useStore();
  const [actual, setActual] = useState(String(balance / 100));
  const [busy, setBusy] = useState(false);
  const actualKop = parseRub(actual);
  const delta = actualKop == null ? null : actualKop - balance;

  const apply = async () => {
    if (actualKop == null) {
      notify({ title: "Balance is not a number", theme: "danger" });
      return;
    }
    setBusy(true);
    try {
      const res = await reconcileAccount(account.id, actualKop);
      notify({
        title: res.delta === 0 ? "Already reconciled" : `Adjustment of ${money(res.delta)} posted`,
        theme: "success",
      });
      onClose();
    } catch (e) {
      notify({ title: "Failed to reconcile", theme: "danger", content: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onClose={onClose} size="s">
      <Dialog.Header caption={`Reconcile ${account.name}`} />
      <Dialog.Body>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <Text color="secondary">Computed balance</Text>
            <span className="num">{money(balance)}</span>
          </div>
          <TextInput label="Actual bank balance" value={actual} onUpdate={setActual} autoFocus />
          {delta != null && delta !== 0 && (
            <Text color="secondary" variant="caption-2">
              An adjustment of {money(delta)} will be posted so the account matches your bank.
            </Text>
          )}
        </div>
      </Dialog.Body>
      <Dialog.Footer
        textButtonApply="Reconcile"
        textButtonCancel="Cancel"
        onClickButtonApply={apply}
        onClickButtonCancel={onClose}
        propsButtonApply={{ loading: busy }}
      />
    </Dialog>
  );
}
