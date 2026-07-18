import { rub } from "../format.js";

export function Money({ value, zeroDim = true, signColor = false }) {
    const cls =
        value === 0 && zeroDim
            ? "money_zero"
            : signColor
              ? value > 0
                  ? "money_pos"
                  : value < 0
                    ? "money_neg"
                    : ""
              : "";
    return <span className={`money num ${cls}`}>{rub(value)}</span>;
}

export function BalancePill({ value }) {
    const cls =
        value > 0 ? "balance-pill_pos" : value < 0 ? "balance-pill_neg" : "balance-pill_zero";
    return <span className={`balance-pill num ${cls}`}>{rub(value)}</span>;
}
