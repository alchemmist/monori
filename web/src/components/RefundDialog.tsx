import { Button, Stack } from "@mantine/core";
import { useEffect, useState } from "react";
import { FSelect } from "../ui/fields.jsx";
import AppDialog from "../ui/AppDialog.jsx";
import { useStore } from "../store.js";
import { fmtDate, money } from "../format.js";
import type { Id, Transaction } from "../types.js";

export default function RefundDialog({
    transaction,
    onClose,
}: {
    transaction: Transaction;
    onClose: () => void;
}) {
    const { refundSuggestions, linkRefund, notify } = useStore();
    const [rows, setRows] = useState<Transaction[]>([]);
    const [originalId, setOriginalId] = useState(
        transaction.refundOfId == null ? "" : String(transaction.refundOfId),
    );
    const [includeAll, setIncludeAll] = useState(false);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        let active = true;
        void refundSuggestions(transaction.id, includeAll)
            .then((suggestions) => {
                if (active) setRows(suggestions);
            })
            .catch((error: unknown) => {
                if (!active) return;
                notify({
                    title: includeAll
                        ? "Failed to load eligible purchases"
                        : "Failed to load refund suggestions",
                    theme: "danger",
                    content: String(error),
                });
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
        };
    }, [includeAll, notify, refundSuggestions, transaction.id]);

    const apply = async () => {
        if (originalId === "") return;
        setBusy(true);
        try {
            await linkRefund(transaction.id, Number(originalId) as Id);
            notify({ title: "Refund linked", theme: "success" });
            onClose();
        } catch (error) {
            notify({ title: "Failed to link refund", theme: "danger", content: String(error) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title="Mark as refund"
            onClose={onClose}
            applyText="Link refund"
            onApply={() => void apply()}
            applyLoading={busy}
            applyDisabled={originalId === ""}
        >
            <Stack gap="xs">
                <FSelect
                    label="Original purchase"
                    value={originalId === "" ? null : originalId}
                    onChange={setOriginalId}
                    data={rows.map((row) => ({
                        value: String(row.id),
                        label: `${fmtDate(row.date)} · ${row.description} · ${money(-row.amount)}`,
                    }))}
                    searchable
                    placeholder="Choose a purchase"
                />
                <Button
                    variant="subtle"
                    loading={loading}
                    disabled={busy}
                    onClick={() => {
                        setLoading(true);
                        setOriginalId("");
                        setIncludeAll((value) => !value);
                    }}
                >
                    {includeAll ? "Show suggestions" : "Show all eligible purchases"}
                </Button>
            </Stack>
        </AppDialog>
    );
}
