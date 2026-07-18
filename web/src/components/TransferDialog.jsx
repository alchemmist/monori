import { useState } from "react";
import { Dialog, TextInput, Select, Text } from "@gravity-ui/uikit";
import { useStore } from "../store.js";
import { parseRub } from "../format.js";

const today = () => new Date().toISOString().slice(0, 10);

export default function TransferDialog({ accounts, onClose }) {
  const { createTransfer, notify } = useStore();
  const active = accounts.filter((a) => !a.archived);
  const [from, setFrom] = useState(active[0] ? String(active[0].id) : "");
  const [to, setTo] = useState(active[1] ? String(active[1].id) : "");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today());
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const amountKop = parseRub(amount);
  const valid = from && to && from !== to && amountKop != null && amountKop > 0;

  const apply = async () => {
    if (!valid) return;
    setBusy(true);
    try {
      await createTransfer({
        fromAccountId: +from,
        toAccountId: +to,
        amount: amountKop,
        date: `${date}T12:00:00`,
        comment: comment.trim(),
      });
      notify({ title: "Transfer created", theme: "success" });
      onClose();
    } catch (e) {
      notify({ title: "Failed to create transfer", theme: "danger", content: String(e) });
    } finally {
      setBusy(false);
    }
  };

  const options = active.map((a) => ({ value: String(a.id), content: a.name }));

  return (
    <Dialog open onClose={onClose} size="s">
      <Dialog.Header caption="Transfer between accounts" />
      <Dialog.Body>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
          <Select
            label="From"
            value={from ? [from] : []}
            onUpdate={(v) => setFrom(v[0])}
            options={options}
            width="max"
          />
          <Select
            label="To"
            value={to ? [to] : []}
            onUpdate={(v) => setTo(v[0])}
            options={options}
            width="max"
          />
          <TextInput label="Amount" value={amount} onUpdate={setAmount} autoFocus />
          <TextInput label="Date" type="date" value={date} onUpdate={setDate} />
          <TextInput label="Comment" value={comment} onUpdate={setComment} />
          {from && to && from === to && (
            <Text color="danger" variant="caption-2">
              Pick two different accounts.
            </Text>
          )}
        </div>
      </Dialog.Body>
      <Dialog.Footer
        textButtonApply="Transfer"
        textButtonCancel="Cancel"
        onClickButtonApply={apply}
        onClickButtonCancel={onClose}
        propsButtonApply={{ loading: busy, disabled: !valid }}
      />
    </Dialog>
  );
}
