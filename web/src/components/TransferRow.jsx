import { ArrowRightArrowLeft, ChevronDown, ChevronRight } from "@gravity-ui/icons";
import RowMenu from "../ui/RowMenu.jsx";
import { money, fmtDate } from "../format.js";

/**
 * One transfer, rendered as a single row where the ledger holds two.
 *
 * The account and category columns are merged away: there is nothing to pick on
 * either leg, and the whole point of the row is to read "out of A, into B" in
 * one line. The amount is shown unsigned and untinted — a transfer nets to zero,
 * so neither red nor green would be telling the truth.
 */
export default function TransferRow({ item, accountName, expanded, onToggle, onSplit, onDelete }) {
    const from = accountName(item.out.accountId);
    const to = accountName(item.in.accountId);
    const sameDay = item.out.date.slice(0, 10) === item.in.date.slice(0, 10);
    const note = item.out.comment || item.in.comment;
    const Chevron = expanded ? ChevronDown : ChevronRight;

    return (
        <tr className="cat-row tx-row_transfer">
            <td style={{ textAlign: "left" }} className="num">
                {fmtDate(item.out.date)}
                {!sameDay && (
                    <span className="tx-transfer__second-date">{fmtDate(item.in.date)}</span>
                )}
            </td>
            <td colSpan={2} style={{ textAlign: "left" }}>
                <button
                    type="button"
                    className="tx-transfer__toggle"
                    onClick={onToggle}
                    aria-expanded={expanded}
                    aria-label={expanded ? "Hide both transactions" : "Show both transactions"}
                >
                    <Chevron width={12} height={12} />
                </button>
                <ArrowRightArrowLeft className="tx-transfer__icon" width={14} height={14} />
                <span className="tx-transfer__route">
                    <span className="tx-transfer__account">{from}</span>
                    <span className="tx-transfer__arrow" aria-label="to">
                        →
                    </span>
                    <span className="tx-transfer__account">{to}</span>
                </span>
                {note && <span className="tx-transfer__note">{note}</span>}
            </td>
            <td>
                <span className="money num tx-transfer__amount">{money(item.amount)}</span>
            </td>
            <td colSpan={2} style={{ textAlign: "left" }}>
                <span className="tx-transfer__label">Transfer</span>
                <RowMenu
                    className="cat-row__menu tx-transfer__menu"
                    label="Transfer actions"
                    items={[
                        [
                            {
                                text: expanded
                                    ? "Hide both transactions"
                                    : "Show both transactions",
                                action: onToggle,
                            },
                            { text: "Split into two transactions", action: onSplit },
                        ],
                        [
                            {
                                text: "Delete both transactions",
                                action: onDelete,
                                theme: "danger",
                            },
                        ],
                    ]}
                />
            </td>
        </tr>
    );
}
