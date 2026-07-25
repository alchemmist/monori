import { useState } from "react";
import { Button } from "@mantine/core";

import { CURRENCIES, currencyName, currencySymbol } from "../currencies.js";
import { isDemo, useStore } from "../store.js";
import "./rates.css";

/** How the number in a row got there — worth saying, because a bundled rate is
 * a guess from the day monori was built and a manual one is somebody's edit. */
const SOURCE_LABEL = {
    pivot: "base",
    cbr: "Bank of Russia",
    manual: "set by hand",
    bundled: "bundled fallback",
};

function RateRow({ rate, base, onSet }) {
    const [draft, setDraft] = useState(null);
    const [busy, setBusy] = useState(false);
    const editable = rate.code !== "RUB";

    const commit = async () => {
        const value = Number(String(draft).replace(",", "."));
        setDraft(null);
        if (!Number.isFinite(value) || value <= 0 || value === rate.rate) return;
        setBusy(true);
        try {
            await onSet(rate.code, value);
        } finally {
            setBusy(false);
        }
    };

    return (
        <tr className={rate.code === base ? "rates__row rates__row_base" : "rates__row"}>
            <th scope="row">
                <span className="rates__code">{rate.code}</span>
                <span className="rates__name">{currencyName(rate.code)}</span>
            </th>
            <td className="rates__value num">
                {editable && draft !== null ? (
                    <input
                        className="rates__input num"
                        value={draft}
                        autoFocus
                        inputMode="decimal"
                        onChange={(e) => setDraft(e.target.value)}
                        onBlur={commit}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") e.currentTarget.blur();
                            if (e.key === "Escape") setDraft(null);
                        }}
                    />
                ) : (
                    <button
                        type="button"
                        className="rates__edit"
                        disabled={!editable || busy}
                        onClick={() => setDraft(String(rate.rate))}
                        title={editable ? "Set this rate by hand" : undefined}
                    >
                        {rate.rate.toFixed(4)} ₽
                    </button>
                )}
            </td>
            <td className="rates__meta">
                {SOURCE_LABEL[rate.source] ?? rate.source}
                {rate.stale && <span className="rates__stale">as of {rate.day}</span>}
            </td>
        </tr>
    );
}

/**
 * The rate table behind every converted number, and the two ways to correct it:
 * pull the day's publication, or type a rate in.
 *
 * Rates are quoted in rubles per unit — one pivot, so any pair of currencies is
 * two lookups. Editing one reprices every transaction it priced.
 */
export default function RatesPanel() {
    const snapshot = useStore((s) => s.snapshot);
    const refreshRates = useStore((s) => s.refreshRates);
    const setRate = useStore((s) => s.setRate);
    const notify = useStore((s) => s.notify);
    const [busy, setBusy] = useState(false);

    const base = snapshot?.baseCurrency ?? "RUB";
    const known = new Set(CURRENCIES.map((c) => c.code));
    const rates = (snapshot?.rates ?? []).filter((r) => known.has(r.code));

    const refresh = async () => {
        setBusy(true);
        try {
            const { repriced } = await refreshRates(30);
            notify({
                title: "Rates updated",
                theme: "success",
                content: repriced
                    ? `${repriced} transactions repriced.`
                    : "Nothing needed repricing.",
            });
        } catch (e) {
            notify({ title: "Could not fetch rates", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    const applyRate = async (code, value) => {
        try {
            const { repriced } = await setRate(code, value);
            notify({
                title: `${code} set to ${value} ${currencySymbol("RUB")}`,
                theme: "success",
                content: repriced ? `${repriced} transactions repriced.` : undefined,
            });
        } catch (e) {
            notify({ title: "Could not set the rate", theme: "danger", content: String(e) });
        }
    };

    return (
        <div className="rates">
            <div className="rates__head">
                <span className="rates__caption">
                    Rubles per unit. Every transaction is converted at the rate for its own date, so
                    a correction here never rewrites a day it did not apply to.
                </span>
                {!isDemo() && (
                    <Button variant="default" size="xs" loading={busy} onClick={refresh}>
                        Fetch today
                    </Button>
                )}
            </div>
            <table className="rates__table">
                <tbody>
                    {rates.map((r) => (
                        <RateRow key={r.code} rate={r} base={base} onSet={applyRate} />
                    ))}
                </tbody>
            </table>
        </div>
    );
}
