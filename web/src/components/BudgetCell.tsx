import { useState } from "react";
import { amountInput, normalizeKop, parseRub, rub } from "../format.js";
import useAmountField from "../ui/useAmountField.js";

/**
 * Inline-editable budget amount. Click (or focus+Enter) to edit; Enter saves,
 * Escape cancels. Recalculation happens in the same frame via the store.
 */
interface BudgetCellProps {
    value: number;
    onChange: (value: number) => void;
    onSelect?: () => void;
    tabIndex?: number;
}

export default function BudgetCell({ value, onChange, onSelect, tabIndex = 0 }: BudgetCellProps) {
    const normalizedValue = normalizeKop(value);
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState("");
    const amount = useAmountField(setDraft);

    const start = () => {
        onSelect?.();
        setDraft(amountInput(normalizedValue));
        setEditing(true);
    };

    const commit = () => {
        const kop = parseRub(draft);
        setEditing(false);
        if (kop !== null && kop !== normalizedValue) onChange(kop);
    };

    if (editing) {
        return (
            <input
                {...amount}
                className="budget-cell__input"
                value={draft}
                autoFocus
                onFocus={(e) => e.target.select()}
                onBlur={commit}
                onKeyDown={(e) => {
                    if (e.key === "Enter") commit();
                    if (e.key === "Escape") setEditing(false);
                    if (e.key === "Tab") commit();
                }}
            />
        );
    }

    return (
        <span
            className="budget-cell money num"
            role="button"
            tabIndex={tabIndex}
            onClick={start}
            onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    start();
                }
            }}
            style={{ color: normalizedValue ? "var(--m-text)" : "var(--m-text-faint)" }}
        >
            {rub(value)}
        </span>
    );
}
