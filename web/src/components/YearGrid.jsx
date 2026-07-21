import { useEffect, useRef } from "react";
import { ActionIcon } from "@mantine/core";
import RowMenu from "../ui/RowMenu.jsx";
import { Plus, ChevronDown, EllipsisVertical } from "@gravity-ui/icons";
import BudgetCell from "./BudgetCell.jsx";
import { rub } from "../format.js";
import { MONTHS_SHORT } from "../format.js";

const METRICS = {
    budgeted: { key: "budgeted", label: "Bud" },
    activity: { key: "activity", label: "Act" },
    balance: { key: "balance", label: "Bal" },
};

/**
 * The whole year on one screen — the Google Sheets year layout rebuilt as a
 * spreadsheet-style frozen grid. Rows are expense categories grouped by their
 * group; every month is a block of Budgeted / Activity / Balance columns, and
 * a Total + Avg pair closes each row. The category column and the header are
 * frozen; editing any Budgeted cell recomputes the whole grid in the same frame.
 *
 * @param cols  which metric columns to show, e.g. ['budgeted','activity','balance']
 */
export default function YearGrid({
    res,
    prevRes,
    groups,
    catsByGroup,
    year,
    currentMonth,
    cols,
    collapsed,
    setCollapsed,
    setBudget,
    onCategoryMenu,
    onAddCategory,
}) {
    const span = cols.length;
    const wrapRef = useRef(null);
    const theadRef = useRef(null);

    // Sticky header without an internal scroll pane: the page scrolls the whole
    // (full-height) table, and this floats the <thead> down to keep the months
    // pinned at the viewport top. Horizontal alignment is native — the thead
    // lives inside the same horizontally-scrolled wrapper as the body.
    useEffect(() => {
        const wrap = wrapRef.current;
        const thead = theadRef.current;
        if (!wrap || !thead) return;
        let raf = 0;
        const update = () => {
            raf = 0;
            const rect = wrap.getBoundingClientRect();
            const maxY = wrap.offsetHeight - thead.offsetHeight;
            const y = rect.top < 0 ? Math.min(-rect.top, Math.max(maxY, 0)) : 0;
            thead.style.transform = y > 0 ? `translateY(${y}px)` : "";
        };
        const onScroll = () => {
            if (!raf) raf = requestAnimationFrame(update);
        };
        window.addEventListener("scroll", onScroll, { passive: true });
        window.addEventListener("resize", onScroll);
        update();
        return () => {
            window.removeEventListener("scroll", onScroll);
            window.removeEventListener("resize", onScroll);
            if (raf) cancelAnimationFrame(raf);
        };
    }, []);

    const metricCell = (metric, { budgeted, outflows, balance }, onEdit) => {
        if (metric === "budgeted") {
            return onEdit ? (
                <BudgetCell value={budgeted} onChange={onEdit} />
            ) : (
                <span className="yg-num">{rub(budgeted)}</span>
            );
        }
        if (metric === "activity") {
            return (
                <span className={`yg-num ${outflows < 0 ? "yg-num_neg" : "yg-num_zero"}`}>
                    {rub(outflows)}
                </span>
            );
        }
        // balance
        const cls = balance > 0 ? "yg-num_pos" : balance < 0 ? "yg-num_neg" : "yg-num_zero";
        return <span className={`yg-num ${cls}`}>{rub(balance)}</span>;
    };

    return (
        <div className="year-grid-wrap" ref={wrapRef}>
            <table className="year-grid">
                <thead ref={theadRef}>
                    {/* header band: the year, then the colored Available-to-budget hero per month */}
                    <tr className="yg-band">
                        <th className="yg-corner yg-corner_year">
                            <div className="yg-year">{year}</div>
                            <div className="yg-year__cap">Available to budget</div>
                        </th>
                        {MONTHS_SHORT.map((m, i) => {
                            const a = res.available[i];
                            const cls = a > 0 ? "yg-num_pos" : a < 0 ? "yg-num_neg" : "yg-num_zero";
                            // the pieces that sum to Available: carry-in + last month's overspend
                            // + this month's income − this month's budgeted
                            const prevName = i > 0 ? MONTHS_SHORT[i - 1] : "Dec";
                            const prevAvail =
                                i > 0 ? res.available[i - 1] : prevRes ? prevRes.available[11] : 0;
                            const prevOver =
                                i > 0 ? res.overspent[i - 1] : prevRes ? prevRes.overspent[11] : 0;
                            return (
                                <th
                                    key={m}
                                    className={`yg-msum ${i === currentMonth ? "yg-msum_now" : ""}`}
                                    colSpan={span}
                                >
                                    <div className="yg-msum__mon">
                                        {m} {year}
                                    </div>
                                    <div className={`yg-msum__av ${cls}`}>{rub(a)} ₽</div>
                                    <div className="yg-msum__break">
                                        <BreakLine
                                            value={prevAvail}
                                            label={`Not budgeted in ${prevName}`}
                                        />
                                        <BreakLine
                                            value={prevOver}
                                            label={`Overspent in ${prevName}`}
                                        />
                                        <BreakLine
                                            value={res.income[i]}
                                            label={`Income for ${m}`}
                                        />
                                        <BreakLine
                                            value={-res.budgetedTotal[i]}
                                            label={`Budgeted in ${m}`}
                                        />
                                    </div>
                                </th>
                            );
                        })}
                        <th className="yg-band__tail" colSpan={2} />
                    </tr>
                    {/* column labels */}
                    <tr className="yg-colhead">
                        <th className="yg-corner yg-corner_cat">Category</th>
                        {MONTHS_SHORT.map((m, i) =>
                            cols.map((metric, j) => (
                                <th
                                    key={`${m}-${metric}`}
                                    className={`yg-metric ${j === 0 ? "yg-metric_first" : ""} ${
                                        i === currentMonth ? "yg-metric_now" : ""
                                    }`}
                                >
                                    {METRICS[metric].label}
                                </th>
                            )),
                        )}
                        <th className="yg-total-head">Total</th>
                        <th className="yg-total-head">Avg</th>
                    </tr>
                </thead>

                <tbody>
                    {groups.map((g) => {
                        const cats = catsByGroup.get(g.id) ?? [];
                        const isCollapsed = collapsed[g.id];

                        // per-month group subtotals + year total of outflows
                        const sub = Array.from({ length: 12 }, () => ({
                            budgeted: 0,
                            outflows: 0,
                            balance: 0,
                        }));
                        let groupYearSpent = 0;
                        for (const c of cats) {
                            const months = res.byCategory.get(c.id);
                            if (!months) continue;
                            for (let m = 0; m < 12; m++) {
                                sub[m].budgeted += months[m].budgeted;
                                sub[m].outflows += months[m].outflows;
                                if (months[m].balance > 0) sub[m].balance += months[m].balance;
                                groupYearSpent += months[m].outflows;
                            }
                        }

                        const rows = [
                            <tr
                                key={`g${g.id}`}
                                className="yg-group"
                                onClick={() => setCollapsed({ ...collapsed, [g.id]: !isCollapsed })}
                            >
                                <td className="yg-name">
                                    <span
                                        className={`yg-chevron ${isCollapsed ? "yg-chevron_collapsed" : ""}`}
                                    >
                                        <ChevronDown width={13} height={13} />
                                    </span>
                                    {g.name}
                                    <span className="yg-count">{cats.length}</span>
                                    <ActionIcon
                                        size={20}
                                        variant="subtle"
                                        className="yg-add"
                                        aria-label="Add category"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onAddCategory(g.id);
                                        }}
                                    >
                                        <Plus width={12} height={12} />
                                    </ActionIcon>
                                </td>
                                {sub.map((s, m) =>
                                    cols.map((metric, j) => (
                                        <td
                                            key={`${m}-${metric}`}
                                            className={`${j === 0 ? "yg-cell_first" : ""} ${m === currentMonth ? "yg-cell_now" : ""}`}
                                        >
                                            {metricCell(metric, s)}
                                        </td>
                                    )),
                                )}
                                <td className="yg-total yg-num_neg">{rub(groupYearSpent)}</td>
                                <td className="yg-total yg-num_dim">
                                    {rub(Math.round(groupYearSpent / 12))}
                                </td>
                            </tr>,
                        ];

                        if (!isCollapsed) {
                            for (const c of cats) {
                                const months = res.byCategory.get(c.id) ?? [];
                                const yearSpent = months.reduce((s, mm) => s + mm.outflows, 0);
                                rows.push(
                                    <tr key={c.id} className="yg-row">
                                        <td className="yg-name">
                                            <div className="yg-name_cat">
                                                <span className="yg-cat-label">{c.name}</span>
                                                <span
                                                    className="yg-row-menu"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    <RowMenu
                                                        size="xs"
                                                        icon={
                                                            <EllipsisVertical
                                                                width={13}
                                                                height={13}
                                                            />
                                                        }
                                                        items={onCategoryMenu(c)}
                                                    />
                                                </span>
                                            </div>
                                        </td>
                                        {months.map((mm, m) =>
                                            cols.map((metric, j) => (
                                                <td
                                                    key={`${m}-${metric}`}
                                                    className={`${j === 0 ? "yg-cell_first" : ""} ${m === currentMonth ? "yg-cell_now" : ""}`}
                                                >
                                                    {metricCell(
                                                        metric,
                                                        mm,
                                                        metric === "budgeted"
                                                            ? (v) => setBudget(c.id, year, m + 1, v)
                                                            : undefined,
                                                    )}
                                                </td>
                                            )),
                                        )}
                                        <td className="yg-total yg-num_neg">{rub(yearSpent)}</td>
                                        <td className="yg-total yg-num_dim">
                                            {rub(Math.round(yearSpent / 12))}
                                        </td>
                                    </tr>,
                                );
                            }
                        }
                        return rows;
                    })}
                </tbody>
            </table>
        </div>
    );
}

function BreakLine({ value, label }) {
    return (
        <div className="yg-break__line">
            <span className={`yg-break__val ${value < 0 ? "yg-num_neg" : ""}`}>{rub(value)}</span>
            <span className="yg-break__lbl">{label}</span>
        </div>
    );
}
