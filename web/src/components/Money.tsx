import { normalizeKop, rub } from "../format.js";

interface MoneyProps {
    value: number;
    zeroDim?: boolean;
    signColor?: boolean;
}

export function Money({ value, zeroDim = true, signColor = false }: MoneyProps) {
    const normalized = normalizeKop(value);
    const cls =
        normalized === 0 && zeroDim
            ? "money_zero"
            : signColor
              ? normalized > 0
                  ? "money_pos"
                  : normalized < 0
                    ? "money_neg"
                    : ""
              : "";
    return <span className={`money num ${cls}`}>{rub(value)}</span>;
}

export function BalancePill({ value }: { value: number }) {
    const normalized = normalizeKop(value);
    const cls =
        normalized > 0
            ? "balance-pill_pos"
            : normalized < 0
              ? "balance-pill_neg"
              : "balance-pill_zero";
    return <span className={`balance-pill num ${cls}`}>{rub(value)}</span>;
}
