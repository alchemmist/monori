import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useStore } from "../store.js";
import { amountInput, parseRub, rubExact } from "../format.js";
import { currencySymbol, normalizeCurrency } from "../currencies.js";
import { convertAmount } from "../money.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FAmountInput, FSelect, FTextInput } from "../ui/fields.jsx";
import Txt from "../ui/Txt.jsx";

const today = () => new Date().toISOString().slice(0, 10);

export default function TransferDialog({ accounts, onClose }) {
    const { createTransfer, notify } = useStore();
    // the data, not the accessor: a rate refreshed while the dialog is open has
    // to move the suggested amount with it
    const rates = useStore((s) => s.snapshot?.rates);
    const active = accounts.filter((a) => !a.archived);
    const [from, setFrom] = useState(active[0] ? String(active[0].id) : "");
    const [to, setTo] = useState(active[1] ? String(active[1].id) : "");
    const [amount, setAmount] = useState("");
    const [landed, setLanded] = useState("");
    const [date, setDate] = useState(today());
    const [comment, setComment] = useState("");
    const [busy, setBusy] = useState(false);
    const [conversionRates, setConversionRates] = useState(rates ?? []);

    useEffect(() => {
        let current = true;
        api.rates(date)
            .then((response) => {
                if (current) setConversionRates(response.rates);
            })
            .catch(() => {
                if (current) setConversionRates(rates ?? []);
            });
        return () => {
            current = false;
        };
    }, [date, rates]);

    const byId = new Map(active.map((a) => [String(a.id), a]));
    const fromCurrency = normalizeCurrency(byId.get(from)?.currency);
    const toCurrency = normalizeCurrency(byId.get(to)?.currency);
    // money crossing a currency line arrives as a different number, and only the
    // person who made the transfer knows which one — the rate is a starting guess
    const crossCurrency = Boolean(from && to && from !== to && fromCurrency !== toCurrency);

    const amountKop = parseRub(amount);
    const landedKop = parseRub(landed);

    // seed the second field from the day's rate whenever the pair or the amount
    // changes, so the common case needs no typing and the odd case is one edit
    useEffect(() => {
        if (!crossCurrency || amountKop == null || amountKop <= 0) return;
        setLanded(amountInput(convertAmount(amountKop, fromCurrency, toCurrency, conversionRates)));
    }, [crossCurrency, amountKop, fromCurrency, toCurrency, conversionRates]);

    const valid =
        from &&
        to &&
        from !== to &&
        amountKop != null &&
        amountKop > 0 &&
        (!crossCurrency || (landedKop != null && landedKop > 0));

    const apply = async () => {
        if (!valid) return;
        setBusy(true);
        try {
            await createTransfer({
                fromAccountId: +from,
                toAccountId: +to,
                amount: amountKop,
                ...(crossCurrency ? { toAmount: landedKop } : {}),
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

    const options = active.map((a) => ({
        value: String(a.id),
        label: `${a.name} · ${normalizeCurrency(a.currency)}`,
    }));

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
                <FAmountInput
                    label={crossCurrency ? `Sent (${fromCurrency})` : "Amount"}
                    value={amount}
                    onChange={setAmount}
                    autoFocus
                />
                {crossCurrency && (
                    <>
                        <FAmountInput
                            label={`Received (${toCurrency})`}
                            value={landed}
                            onChange={setLanded}
                        />
                        <Txt tone="secondary" caption>
                            Filled in at the selected date&apos;s rate — replace it with what
                            actually arrived, since a bank converts at its own.
                            {amountKop > 0 && landedKop > 0 && (
                                <>
                                    {" "}
                                    That is {rubExact(
                                        Math.round((amountKop * 100) / landedKop),
                                    )}{" "}
                                    {currencySymbol(fromCurrency)} per {toCurrency}.
                                </>
                            )}
                        </Txt>
                    </>
                )}
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
