import { useEffect, useState } from "react";
import { Button } from "@mantine/core";
import { useStore } from "../store.js";
import { money, fmtDate } from "../format.js";
import AppDialog from "../ui/AppDialog.jsx";
import Txt from "../ui/Txt.jsx";

/**
 * Pairs that look like a transfer but did not land close enough in time for the
 * server to merge them unasked. Each one is confirmed or dismissed by hand;
 * dismissing is remembered, so the same pair is never offered twice.
 */
export default function TransferSuggestions({ onClose }) {
    const {
        snapshot,
        transferSuggestions,
        linkTransfer,
        dismissTransferSuggestion,
        detectTransfers,
        notify,
    } = useStore();
    const [state, setState] = useState({ loading: true, rows: [], byId: new Map() });
    const [busy, setBusy] = useState(null);

    const acctName = new Map((snapshot.accounts ?? []).map((a) => [a.id, a.name]));

    const refresh = async () => {
        setState((s) => ({ ...s, loading: true }));
        try {
            const { rows, transactions } = await transferSuggestions();
            setState({
                loading: false,
                rows,
                byId: new Map(transactions.map((t) => [t.id, t])),
            });
        } catch (e) {
            setState({ loading: false, rows: [], byId: new Map() });
            notify({ title: "Failed to look for transfers", theme: "danger", content: String(e) });
        }
    };

    useEffect(() => {
        // a scan first, so anything unambiguous is merged rather than listed
        detectTransfers().then(refresh, refresh);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const act = (pair, fn) => async () => {
        setBusy(`${pair.outTxId}-${pair.inTxId}`);
        try {
            await fn();
            setState((s) => ({
                ...s,
                rows: s.rows.filter((p) => p.outTxId !== pair.outTxId || p.inTxId !== pair.inTxId),
            }));
        } catch (e) {
            notify({ title: "Failed to update the pair", theme: "danger", content: String(e) });
        } finally {
            setBusy(null);
        }
    };

    return (
        <AppDialog title="Possible transfers" onClose={onClose} applyText="Done" onApply={onClose}>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 4 }}>
                {state.loading && <Txt caption>Looking for pairs…</Txt>}
                {!state.loading && state.rows.length === 0 && (
                    <Txt caption>
                        Nothing left to confirm — matching pairs on the same day are merged
                        automatically.
                    </Txt>
                )}
                {state.rows.map((pair) => {
                    const out = state.byId.get(pair.outTxId);
                    const inLeg = state.byId.get(pair.inTxId);
                    if (!out || !inLeg) return null;
                    const key = `${pair.outTxId}-${pair.inTxId}`;
                    return (
                        <div key={key} className="tx-suggestion">
                            <div className="tx-suggestion__route">
                                <span>{acctName.get(out.accountId) ?? "—"}</span>
                                <span aria-label="to">→</span>
                                <span>{acctName.get(inLeg.accountId) ?? "—"}</span>
                                <span className="money num">{money(pair.amount)}</span>
                            </div>
                            <Txt caption>
                                {fmtDate(out.date)} → {fmtDate(inLeg.date)} ·{" "}
                                {pair.days === 1 ? "1 day apart" : `${pair.days} days apart`}
                            </Txt>
                            {(out.description || inLeg.description) && (
                                <Txt caption tone={pair.mismatch ? "danger" : "secondary"}>
                                    {out.description || "—"} → {inLeg.description || "—"}
                                </Txt>
                            )}
                            <div className="tx-suggestion__actions">
                                <Button
                                    size="xs"
                                    variant="filled"
                                    loading={busy === key}
                                    onClick={act(pair, () =>
                                        linkTransfer(pair.outTxId, pair.inTxId),
                                    )}
                                >
                                    Merge
                                </Button>
                                <Button
                                    size="xs"
                                    variant="default"
                                    loading={busy === key}
                                    onClick={act(pair, () =>
                                        dismissTransferSuggestion(pair.outTxId, pair.inTxId),
                                    )}
                                >
                                    Not a transfer
                                </Button>
                            </div>
                        </div>
                    );
                })}
            </div>
        </AppDialog>
    );
}
