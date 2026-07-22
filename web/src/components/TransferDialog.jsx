import { useState } from "react";
import { useStore } from "../store.js";
import { parseRub } from "../format.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FSelect, FTextInput } from "../ui/fields.jsx";
import Txt from "../ui/Txt.jsx";

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

    const options = active.map((a) => ({ value: String(a.id), label: a.name }));

    return (
        <AppDialog
            title="Transfer between accounts"
            onClose={onClose}
            applyText="Transfer"
            onApply={apply}
            applyLoading={busy}
            applyDisabled={!valid}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <FSelect label="From" value={from || null} onChange={setFrom} data={options} />
                <FSelect label="To" value={to || null} onChange={setTo} data={options} />
                <FTextInput
                    label="Amount"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    autoFocus
                />
                <FTextInput
                    label="Date"
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                />
                <FTextInput
                    label="Comment"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                />
                {from && to && from === to && (
                    <Txt tone="danger" caption>
                        Pick two different accounts.
                    </Txt>
                )}
            </div>
        </AppDialog>
    );
}
