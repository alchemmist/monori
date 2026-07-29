import { useEffect, useState } from "react";
import { useStore } from "../store.js";
import { money, fmtDate } from "../format.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FSelect } from "../ui/fields.jsx";
import Txt from "../ui/Txt.jsx";

export default function RefundDialog({ transaction, onClose }) {
    const { refundSuggestions, linkRefund, notify } = useStore();
    const [rows, setRows] = useState([]);
    const [originalId, setOriginalId] = useState(
        transaction.refundOfId ? String(transaction.refundOfId) : null,
    );
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        let live = true;
        refundSuggestions(transaction.id)
            .then((suggestions) => live && setRows(suggestions))
            .catch((error) =>
                notify({ title: "Failed to find purchases", content: String(error), theme: "danger" }),
            )
            .finally(() => live && setLoading(false));
        return () => {
            live = false;
        };
    }, [notify, refundSuggestions, transaction.id]);

    const options = rows.map((row) => ({
        value: String(row.id),
        label: `${fmtDate(row.date)} · ${row.description || "No description"} · ${money(row.amount)}`,
    }));

    const apply = async () => {
        if (!originalId) return;
        setBusy(true);
        try {
            await linkRefund(transaction.id, +originalId);
            notify({ title: "Refund linked to purchase", theme: "success" });
            onClose();
        } catch (error) {
            notify({ title: "Failed to link refund", content: String(error), theme: "danger" });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title="Mark as refund of…"
            onClose={onClose}
            applyText="Link refund"
            onApply={apply}
            applyLoading={busy}
            applyDisabled={!originalId || loading}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <Txt caption tone="secondary">
                    {money(transaction.amount)} · {transaction.description || "No description"}
                </Txt>
                <FSelect
                    label="Original purchase"
                    placeholder={loading ? "Finding recent purchases…" : "Choose a purchase"}
                    value={originalId}
                    onChange={setOriginalId}
                    data={options}
                    searchable
                    disabled={loading}
                />
                {!loading && !options.length && (
                    <Txt caption tone="secondary">No purchase with enough refundable amount found.</Txt>
                )}
            </div>
        </AppDialog>
    );
}
