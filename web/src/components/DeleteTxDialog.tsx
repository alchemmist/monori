import { useState } from "react";
import { Button } from "@mantine/core";
import AppDialog from "../ui/AppDialog.jsx";
import Txt from "../ui/Txt.jsx";
import { useStore } from "../store.js";
import { money, fmtDate } from "../format.js";
import type { Transaction } from "../types.js";

/**
 * Confirm before a transaction is gone for good. Deleting is not the same as
 * hiding — a hidden row can be brought back from the Hidden toggle, this one
 * cannot — so the dialog spells the row out and says which of the two you want.
 */
export default function DeleteTxDialog({ tx, onClose }: { tx: Transaction; onClose: () => void }) {
    const { deleteTransaction, hideTx, notify } = useStore();
    const [busy, setBusy] = useState(false);

    const apply = async () => {
        setBusy(true);
        try {
            if (await deleteTransaction(tx.id)) {
                notify({ title: "Transaction deleted", theme: "success" });
                onClose();
            }
        } catch (e) {
            notify({ title: "Failed to delete transaction", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title="Delete transaction"
            onClose={onClose}
            applyText="Delete"
            onApply={() => void apply()}
            applyLoading={busy}
            applyDanger
        >
            <Txt block>
                {fmtDate(tx.date)} · {tx.description || "no description"} · {money(tx.amount)}
            </Txt>
            <Txt block tone="secondary">
                This removes the row for good and every total that counts it. To keep it out of the
                budget without losing it, hide it instead.
            </Txt>
            <Button
                variant="subtle"
                onClick={() => {
                    hideTx(tx.id);
                    onClose();
                }}
                style={{ paddingInline: 0 }}
            >
                Hide it instead
            </Button>
        </AppDialog>
    );
}
