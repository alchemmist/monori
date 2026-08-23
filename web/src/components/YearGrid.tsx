import { useLayoutEffect, useRef } from "react";
import { ActionIcon } from "@mantine/core";
import RowMenu from "../ui/RowMenu.jsx";
import { Plus, ChevronDown, EllipsisVertical } from "@gravity-ui/icons";
import BudgetCell from "./BudgetCell.jsx";
import { MONTHS_SHORT, normalizeKop, rub } from "../format.js";
import GoalCategoryLabel from "./GoalCategoryLabel.jsx";
import type { CSSProperties } from "react";
import type { BudgetCell as BudgetCellModel, Category, CategoryGroup, Id } from "../types.js";
import type { BudgetMonth, BudgetYearResult } from "../engine/budget.js";
import type { RowMenuItem } from "../ui/RowMenu.js";
import type { goalProgress } from "../engine/goals.js";

const METRICS = {
    budgeted: { key: "budgeted", label: "Bud" },
    activity: { key: "activity", label: "Act" },
    balance: { key: "balance", label: "Bal" },
};

type Metric = keyof typeof METRICS;
type GoalProgress = ReturnType<typeof goalProgress>;
type GoalStyle = CSSProperties & { "--goal-progress"?: string };

interface YearGridProps {
    res: BudgetYearResult;
    prevRes: BudgetYearResult | null;
    groups: CategoryGroup[];
    catsByGroup: Map<Id, Category[]>;
    year: number;
    currentMonth: number;
    completeMonth?: number;
    cols: Metric[];
    collapsed: Record<number, boolean>;
    setCollapsed: (collapsed: Record<number, boolean>) => void;
    setBudget: (categoryId: Id, year: number, month: number, amount: number) => void;
    onSelectBudget?: (cell: Omit<BudgetCellModel, "amount">) => void;
    onCategoryMenu: (category: Category) => RowMenuItem[] | RowMenuItem[][];
    onAddCategory: (groupId: Id) => void;
    goalProgressFor?: (category: Category) => GoalProgress | null | undefined;
}

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
    completeMonth = -1,
    cols,
    collapsed,
    setCollapsed,
    setBudget,
    onSelectBudget,
    onCategoryMenu,
    onAddCategory,
    goalProgressFor,
}: YearGridProps) {
    const span = cols.length;
    const metricWidth = Math.max(82, Math.ceil(228 / span));
    const tableWidth = 210 + 12 * span * metricWidth + 164;
    const wrapRef = useRef<HTMLDivElement>(null);

    // The wrap is its own scroll pane filling the viewport below the toolbar, so
    // the header and the category column pin with native position:sticky — no
    // per-scroll JS. The only measurement is the pane's top offset (toolbar and
    // demo banner heights vary), taken on mount and on layout changes, never on
    // scroll; CSS turns it into the pane height.
    useLayoutEffect(() => {
        const wrap = wrapRef.current;
        if (!wrap) return;
        const fit = () => {
            const top = Math.max(0, Math.round(wrap.getBoundingClientRect().top + window.scrollY));
            wrap.style.setProperty("--yg-top", `${top}px`);
        };
        fit();
        const ro = new ResizeObserver(fit);
        ro.observe(document.body);
        window.addEventListener("resize", fit);
        return () => {
            ro.disconnect();
            window.removeEventListener("resize", fit);
        };
    }, []);

    const metricCell = (
        metric: Metric,
        { budgeted, outflows, balance }: BudgetMonth,
        onEdit?: (value: number) => void,
    ) => {
        if (metric === "budgeted") {
            return onEdit ? (
                <BudgetCell value={budgeted} onChange={onEdit} />
            ) : (
                <span className="yg-num">{rub(budgeted)}</span>
            );
        }
        if (metric === "activity") {
            return (
                <span
                    className={`yg-num ${normalizeKop(outflows) < 0 ? "yg-num_neg" : "yg-num_zero"}`}
                >
                    {rub(outflows)}
                </span>
            );
        }
        // balance
        const normalized = normalizeKop(balance);
        const cls = normalized > 0 ? "yg-num_pos" : normalized < 0 ? "yg-num_neg" : "yg-num_zero";
        return <span className={`yg-num ${cls}`}>{rub(balance)}</span>;
    };

    return (
        <div
            className="year-grid-wrap"
            ref={wrapRef}
            role="region"
            tabIndex={0}
            aria-label="Year budget grid"
        >
            <table className="year-grid" style={{ width: tableWidth }}>
                <colgroup>
                    <col style={{ width: 210 }} />
                    {MONTHS_SHORT.flatMap((m) =>
                        cols.map((metric) => (
                            <col key={`${m}-${metric}`} style={{ width: metricWidth }} />
                        )),
                    )}
                    <col style={{ width: 82 }} />
                    <col style={{ width: 82 }} />
                </colgroup>
                <thead>
                    {/* header band: the year, then the colored Available-to-budget hero per month */}
                    <tr className="yg-band">
                        <th className="yg-corner yg-corner_year">
                            <div className="yg-year">{year}</div>
                            <div className="yg-year__cap">Available to budget</div>
                        </th>
                        {MONTHS_SHORT.map((m, i) => {
                            const a = res.available[i]!;
                            const normalized = normalizeKop(a);
                            const cls =
                                normalized > 0
                                    ? "yg-num_pos"
                                    : normalized < 0
                                      ? "yg-num_neg"
                                      : "yg-num_zero";
                            // the pieces that sum to Available: carry-in + last month's overspend
                            // + this month's income − this month's budgeted
                            const prevName = i > 0 ? MONTHS_SHORT[i - 1] : "Dec";
                            const prevAvail =
                                i > 0
                                    ? res.available[i - 1]!
                                    : prevRes
                                      ? prevRes.available[11]!
                                      : 0;
                            const prevOver =
                                i > 0
                                    ? res.overspent[i - 1]!
                                    : prevRes
                                      ? prevRes.overspent[11]!
                                      : 0;
                            return (
                                <th
                                    key={m}
                                    className={`yg-msum ${i === currentMonth ? "yg-msum_now" : ""} ${i === completeMonth ? "yg-msum_complete" : ""}`}
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
                                            value={res.income[i]!}
                                            label={`Income for ${m}`}
                                        />
                                        <BreakLine
                                            value={-res.budgetedTotal[i]!}
                                            label={`Budgeted in ${m}`}
                                        />
                                    </div>
                                </th>
                            );
                        })}
                        <th className="yg-band__tail" colSpan={2}>
                            <span className="yg-visually-hidden">Year totals</span>
                        </th>
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
                                sub[m]!.budgeted += months[m]!.budgeted;
                                sub[m]!.outflows += months[m]!.outflows;
                                if (months[m]!.balance > 0) sub[m]!.balance += months[m]!.balance;
                                groupYearSpent += months[m]!.outflows;
                            }
                        }

                        const rows = [
                            <tr
                                key={`g${g.id}`}
                                className="yg-group"
                                onClick={() =>
                                    setCollapsed({ ...collapsed, [g.id]: isCollapsed !== true })
                                }
                            >
                                <td className="yg-name">
                                    <span
                                        className={`yg-chevron ${isCollapsed === true ? "yg-chevron_collapsed" : ""}`}
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

                        if (isCollapsed !== true) {
                            for (const c of cats) {
                                const goal = goalProgressFor?.(c);
                                const months = res.byCategory.get(c.id) ?? [];
                                const yearSpent = months.reduce((s, mm) => s + mm.outflows, 0);
                                rows.push(
                                    <tr key={c.id} className="yg-row">
                                        <td
                                            className={`yg-name ${goal ? "goal-category-cell" : ""}`}
                                            style={
                                                goal
                                                    ? ({
                                                          "--goal-progress": `${goal.percent}%`,
                                                      } as GoalStyle)
                                                    : undefined
                                            }
                                        >
                                            <div className="yg-name_cat">
                                                <div className="yg-cat-content">
                                                    <span className="yg-cat-label">
                                                        <GoalCategoryLabel
                                                            name={c.name}
                                                            {...(goal === undefined
                                                                ? {}
                                                                : { progress: goal })}
                                                        />
                                                    </span>
                                                </div>
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
                                                    {metric === "budgeted" ? (
                                                        <BudgetCell
                                                            value={mm.budgeted}
                                                            onChange={(v) =>
                                                                setBudget(c.id, year, m + 1, v)
                                                            }
                                                            onSelect={() =>
                                                                onSelectBudget?.({
                                                                    categoryId: c.id,
                                                                    year,
                                                                    month: m + 1,
                                                                })
                                                            }
                                                        />
                                                    ) : (
                                                        metricCell(metric, mm)
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

function BreakLine({ value, label }: { value: number; label: string }) {
    return (
        <div className="yg-break__line">
            <span className={`yg-break__val ${value < 0 ? "yg-num_neg" : ""}`}>{rub(value)}</span>
            <span className="yg-break__lbl">{label}</span>
        </div>
    );
}
