import { useEffect, useMemo, useRef, useState } from "react";
import { ActionIcon, Button, SegmentedControl } from "@mantine/core";
import InlineSelect from "../ui/InlineSelect.jsx";
import RowMenu from "../ui/RowMenu.jsx";
import { Plus, ChevronDown, EllipsisVertical } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { orderedGroups, categoriesByGroup } from "../categoryOrder.js";
import { MONTHS_SHORT, MONTHS, rub } from "../format.js";
import BudgetCell from "../components/BudgetCell.jsx";
import { Money, BalancePill } from "../components/Money.jsx";
import { CategoryEditDialog, CategoryDeleteDialog } from "../components/CategoryDialogs.jsx";
import YearGrid from "../components/YearGrid.jsx";
import AppDialog from "../ui/AppDialog.jsx";
import { FTextInput } from "../ui/fields.jsx";
import { goalProgress } from "../engine/goals.js";
import GoalCategoryLabel from "../components/GoalCategoryLabel.jsx";
import "../components/yeargrid.css";
import "./budget.css";
import { effectiveTransactions } from "../engine/splits.js";

const YEAR_DENSITY = {
    full: ["budgeted", "activity", "balance"],
    plan: ["budgeted"],
    actual: ["activity", "balance"],
};

export default function BudgetPage({ results, firstYear, lastYear }) {
    const {
        snapshot,
        setBudget,
        setBudgets,
        fillBudgetForward,
        archiveGoal,
        patchCategory,
        notify,
    } = useStore();
    const now = new Date();
    const todayYear = now.getFullYear();
    const todayMonth = now.getMonth() + 1;
    const [year, setYear] = useState(now.getFullYear());
    const [month, setMonth] = useState(now.getMonth()); // 0-based
    const [mode, setMode] = useState("year");
    const [density, setDensity] = useState("full");
    const [collapsed, setCollapsed] = useState({});
    const [showUnused, setShowUnused] = useState(false);
    const [dialog, setDialog] = useState(null); // {type: 'edit'|'delete'|'new', category}
    const [selectedBudgetCell, setSelectedBudgetCell] = useState(null);
    const [fillingForward, setFillingForward] = useState(false);
    const [budgetComplete, setBudgetComplete] = useState(false);
    const celebrationArmed = useRef(true);
    const rearmTimer = useRef(null);

    const res = results.get(year);
    const groups = useMemo(
        () => [
            ...orderedGroups(snapshot.groups).filter((g) => g.kind === "expense"),
            ...orderedGroups(snapshot.groups).filter((g) => g.kind === "goal"),
        ],
        [snapshot.groups],
    );
    const allCatsByGroup = useMemo(
        () => categoriesByGroup(snapshot.categories, groups),
        [snapshot.categories, groups],
    );

    // a category the selected year never touched — nothing budgeted, nothing
    // spent, no balance sitting in the envelope — is noise in every view; a
    // carried balance keeps it visible, since hiding money would be worse
    const { catsByGroup, unusedCount } = useMemo(() => {
        const used = (c) =>
            (res.byCategory.get(c.id) ?? []).some(
                (m) => m.budgeted !== 0 || m.outflows !== 0 || m.balance !== 0,
            );
        let unused = 0;
        const filtered = new Map();
        const kinds = new Map(groups.map((g) => [g.id, g.kind]));
        for (const [gid, cats] of allCatsByGroup) {
            if (kinds.get(gid) === "goal") {
                const current = cats.filter(
                    (c) =>
                        goalProgress(c, snapshot.budgets, todayYear, todayMonth).status ===
                        "active",
                );
                unused += cats.length - current.length;
                filtered.set(gid, showUnused ? cats : current);
                continue;
            }
            const active = cats.filter((c) => {
                if (c.archived) return false;
                return used(c);
            });
            unused += cats.length - active.length;
            filtered.set(gid, showUnused ? cats.filter((c) => !c.archived) : active);
        }
        return { catsByGroup: filtered, unusedCount: unused };
    }, [allCatsByGroup, groups, res, showUnused, snapshot.budgets, todayMonth, todayYear]);

    const txCountByCat = useMemo(() => {
        const m = new Map();
        for (const t of effectiveTransactions(snapshot.transactions)) {
            if (t.categoryId != null) m.set(t.categoryId, (m.get(t.categoryId) ?? 0) + 1);
        }
        return m;
    }, [snapshot.transactions]);

    const years = [];
    for (let y = firstYear; y <= lastYear; y++) years.push(y);

    const available = res.available[month];
    const overspent = res.overspent[month];
    const income = res.income[month];
    const budgetedTotal = res.budgetedTotal[month];

    useEffect(() => {
        clearTimeout(rearmTimer.current);
        celebrationArmed.current = true;
        setBudgetComplete(false);
    }, [year, month]);

    useEffect(() => {
        if (available === 0) return;
        setBudgetComplete(false);
        clearTimeout(rearmTimer.current);
        if (!celebrationArmed.current) {
            rearmTimer.current = setTimeout(() => {
                celebrationArmed.current = true;
            }, 3000);
        }
        return () => clearTimeout(rearmTimer.current);
    }, [available]);

    const saveBudget = async (categoryId, targetYear, targetMonth, amount) => {
        const target = results.get(targetYear);
        const previous = target?.byCategory.get(categoryId)?.[targetMonth - 1]?.budgeted ?? 0;
        const before = target?.available[targetMonth - 1];
        const hitsZero = before !== 0 && before - (amount - previous) === 0;
        await setBudget(categoryId, targetYear, targetMonth, amount);
        if (
            mode === "month" &&
            targetYear === year &&
            targetMonth === month + 1 &&
            hitsZero &&
            celebrationArmed.current
        ) {
            celebrationArmed.current = false;
            setBudgetComplete(true);
        }
    };

    const catMenu = (c) => {
        const goal = groups.find((g) => g.id === c.groupId)?.kind === "goal";
        const toggleGoal = async () => {
            try {
                if (c.archived) {
                    await patchCategory(c.id, { archived: false, goalStatus: "active" });
                } else {
                    await archiveGoal(c.id);
                }
            } catch (e) {
                notify({ title: "Failed to update goal", content: String(e), theme: "danger" });
            }
        };
        return [
            { action: () => setDialog({ type: "edit", category: c }), text: "Edit" },
            ...(goal
                ? [
                      {
                          action: () =>
                              setDialog({
                                  type: c.goalTarget > 0 ? "distribute" : "edit",
                                  category: c,
                              }),
                          text: c.goalTarget > 0 ? "Distribute across months" : "Set target first",
                      },
                      {
                          action: toggleGoal,
                          text: c.archived ? "Open goal" : "Close goal",
                      },
                  ]
                : []),
            {
                action: () => setDialog({ type: "delete", category: c }),
                text: "Delete",
                theme: "danger",
            },
        ];
    };

    const selectedCategory = selectedBudgetCell
        ? snapshot.categories.find((c) => c.id === selectedBudgetCell.categoryId)
        : null;
    const canFillForward = selectedBudgetCell?.month < 12 && selectedCategory;

    const fillForward = async () => {
        if (!canFillForward) return;
        setFillingForward(true);
        try {
            const count = await fillBudgetForward(
                selectedBudgetCell.categoryId,
                selectedBudgetCell.year,
                selectedBudgetCell.month,
            );
            notify({
                title: "Budget filled through December",
                content: `${selectedCategory.name}: ${count} month${count === 1 ? "" : "s"}`,
                theme: "success",
            });
        } catch (e) {
            notify({ title: "Failed to fill budget", content: String(e), theme: "danger" });
        } finally {
            setFillingForward(false);
        }
    };

    return (
        <div className="fade-in">
            <div className="budget-toolbar">
                <h1 className="page-title" style={{ margin: 0 }}>
                    Budget
                </h1>
                <InlineSelect
                    value={String(year)}
                    onChange={(v) => setYear(+v)}
                    data={years.map((y) => String(y))}
                />
                {mode === "month" && (
                    <div className="toolbar-scroll">
                        <SegmentedControl
                            value={String(month)}
                            onChange={(v) => setMonth(+v)}
                            data={MONTHS_SHORT.map((m, i) => ({ value: String(i), label: m }))}
                        />
                    </div>
                )}
                <div style={{ flex: 1 }} />
                {canFillForward && (
                    <Button
                        size="xs"
                        variant="light"
                        loading={fillingForward}
                        onClick={fillForward}
                        title={`Replace ${selectedCategory.name}'s remaining ${selectedBudgetCell.year} budgets with this value`}
                    >
                        Fill {selectedCategory.name} to Dec
                    </Button>
                )}
                {unusedCount > 0 && (
                    <Button
                        size="xs"
                        variant="subtle"
                        onClick={() => setShowUnused((v) => !v)}
                        title="Categories with nothing budgeted, spent or held this year"
                    >
                        {showUnused ? "Hide unused" : `Show ${unusedCount} unused`}
                    </Button>
                )}
                {mode === "year" && (
                    <SegmentedControl
                        value={density}
                        onChange={setDensity}
                        data={[
                            { value: "full", label: "Full" },
                            { value: "plan", label: "Plan" },
                            { value: "actual", label: "Actual" },
                        ]}
                    />
                )}
                <SegmentedControl
                    value={mode}
                    onChange={setMode}
                    data={[
                        { value: "month", label: "Month" },
                        { value: "year", label: "Year" },
                    ]}
                />
            </div>

            {mode === "month" && (
                <>
                    <div className="budget-hero">
                        <div
                            className={`card hero-card hero-card_available ${budgetComplete ? "hero-card_complete" : ""}`}
                        >
                            <div className="hero-card__label" role="status">
                                {budgetComplete && (
                                    <svg
                                        className="hero-card__check"
                                        viewBox="0 0 16 16"
                                        aria-hidden="true"
                                    >
                                        <path d="M3 8.5 6.5 12 13 4.5" />
                                    </svg>
                                )}
                                {budgetComplete ? "All money assigned" : "Available to budget"}
                            </div>
                            <div
                                className="hero-card__value num"
                                style={{
                                    color: available < 0 ? "var(--m-expense)" : "var(--m-income)",
                                }}
                            >
                                {rub(available)} ₽
                            </div>
                            <div className="hero-card__hint">end of {MONTHS[month]}</div>
                        </div>
                        <div className="card hero-card">
                            <div className="hero-card__label">Income</div>
                            <div className="hero-card__value num">{rub(income)} ₽</div>
                            <div className="hero-card__hint">
                                {MONTHS[month]} {year}
                            </div>
                        </div>
                        <div className="card hero-card">
                            <div className="hero-card__label">Budgeted</div>
                            <div className="hero-card__value num">{rub(budgetedTotal)} ₽</div>
                            <div className="hero-card__hint">across all categories</div>
                        </div>
                        <div className="card hero-card">
                            <div className="hero-card__label">Overspent</div>
                            <div
                                className="hero-card__value num"
                                style={{
                                    color:
                                        overspent < 0 ? "var(--m-expense)" : "var(--m-text-faint)",
                                }}
                            >
                                {rub(overspent)} ₽
                            </div>
                            <div className="hero-card__hint">uncovered this month</div>
                        </div>
                    </div>

                    <div className="card budget-month-card" style={{ overflow: "hidden" }}>
                        <table className="budget-grid">
                            <thead>
                                <tr>
                                    <th>Category</th>
                                    <th>Budgeted</th>
                                    <th>Activity</th>
                                    <th>Balance</th>
                                    <th style={{ width: 36 }} />
                                </tr>
                            </thead>
                            <tbody>
                                {groups.map((g) => {
                                    const cats = catsByGroup.get(g.id) ?? [];
                                    const isCollapsed = collapsed[g.id];
                                    let gb = 0,
                                        go = 0,
                                        gbal = 0;
                                    for (const c of cats) {
                                        const m = res.byCategory.get(c.id)?.[month];
                                        if (!m) continue;
                                        gb += m.budgeted;
                                        go += m.outflows;
                                        if (m.balance > 0) gbal += m.balance;
                                    }
                                    return [
                                        <tr
                                            key={`g${g.id}`}
                                            className="group-row"
                                            onClick={() =>
                                                setCollapsed({ ...collapsed, [g.id]: !isCollapsed })
                                            }
                                        >
                                            <td>
                                                <span
                                                    className={`group-row__chevron ${isCollapsed ? "group-row__chevron_collapsed" : ""}`}
                                                >
                                                    <ChevronDown width={14} height={14} />
                                                </span>
                                                {g.name}
                                                {g.kind === "goal" && (
                                                    <span className="goal-group-badge">Goals</span>
                                                )}
                                                <span className="group-row__count">
                                                    {cats.length}
                                                </span>
                                                <ActionIcon
                                                    size={20}
                                                    variant="subtle"
                                                    style={{ marginLeft: 8 }}
                                                    aria-label="Add category"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setDialog({
                                                            type: "edit",
                                                            category: { groupId: g.id },
                                                        });
                                                    }}
                                                >
                                                    <Plus width={12} height={12} />
                                                </ActionIcon>
                                            </td>
                                            <td>
                                                <Money value={gb} />
                                            </td>
                                            <td>
                                                <Money value={go} signColor />
                                            </td>
                                            <td>
                                                <Money value={gbal} />
                                            </td>
                                            <td />
                                        </tr>,
                                        !isCollapsed &&
                                            cats.map((c) => {
                                                const m = res.byCategory.get(c.id)?.[month] ?? {
                                                    budgeted: 0,
                                                    outflows: 0,
                                                    balance: 0,
                                                };
                                                const progress =
                                                    g.kind === "goal"
                                                        ? goalProgress(
                                                              c,
                                                              snapshot.budgets,
                                                              todayYear,
                                                              todayMonth,
                                                          )
                                                        : null;
                                                const spentRatio =
                                                    m.budgeted > 0
                                                        ? Math.min(1, -m.outflows / m.budgeted)
                                                        : m.outflows < 0
                                                          ? 1
                                                          : 0;
                                                return (
                                                    <tr key={c.id} className="cat-row">
                                                        <td
                                                            className={
                                                                progress
                                                                    ? "goal-category-cell"
                                                                    : undefined
                                                            }
                                                            style={
                                                                progress
                                                                    ? {
                                                                          "--goal-progress": `${progress.percent}%`,
                                                                      }
                                                                    : undefined
                                                            }
                                                        >
                                                            <span className="cat-row__name">
                                                                <GoalCategoryLabel
                                                                    name={c.name}
                                                                    progress={progress}
                                                                    urgency={
                                                                        progress ? (
                                                                            <GoalUrgency
                                                                                goal={c}
                                                                                funded={
                                                                                    progress.funded
                                                                                }
                                                                            />
                                                                        ) : null
                                                                    }
                                                                />
                                                                {!progress && (
                                                                    <span className="cat-progress">
                                                                        <span
                                                                            className="cat-progress__fill"
                                                                            style={{
                                                                                width: `${spentRatio * 100}%`,
                                                                                background:
                                                                                    m.balance < 0
                                                                                        ? "var(--m-expense)"
                                                                                        : "var(--m-accent)",
                                                                            }}
                                                                        />
                                                                    </span>
                                                                )}
                                                            </span>
                                                        </td>
                                                        <td>
                                                            <BudgetCell
                                                                value={m.budgeted}
                                                                onSelect={() =>
                                                                    setSelectedBudgetCell({
                                                                        categoryId: c.id,
                                                                        year,
                                                                        month: month + 1,
                                                                    })
                                                                }
                                                                onChange={(v) =>
                                                                    saveBudget(
                                                                        c.id,
                                                                        year,
                                                                        month + 1,
                                                                        v,
                                                                    )
                                                                }
                                                            />
                                                        </td>
                                                        <td>
                                                            <Money value={m.outflows} signColor />
                                                        </td>
                                                        <td>
                                                            <BalancePill value={m.balance} />
                                                        </td>
                                                        <td>
                                                            <span
                                                                className="cat-row__menu"
                                                                onClick={(e) => e.stopPropagation()}
                                                            >
                                                                <RowMenu
                                                                    size="xs"
                                                                    icon={
                                                                        <EllipsisVertical
                                                                            width={14}
                                                                            height={14}
                                                                        />
                                                                    }
                                                                    items={catMenu(c)}
                                                                />
                                                            </span>
                                                        </td>
                                                    </tr>
                                                );
                                            }),
                                    ];
                                })}
                            </tbody>
                        </table>
                    </div>
                </>
            )}

            {mode === "year" && (
                <YearGrid
                    res={res}
                    prevRes={results.get(year - 1) ?? null}
                    groups={groups}
                    catsByGroup={catsByGroup}
                    year={year}
                    currentMonth={year === now.getFullYear() ? now.getMonth() : -1}
                    cols={YEAR_DENSITY[density]}
                    collapsed={collapsed}
                    setCollapsed={setCollapsed}
                    setBudget={saveBudget}
                    onSelectBudget={setSelectedBudgetCell}
                    onAddCategory={(groupId) => setDialog({ type: "edit", category: { groupId } })}
                    onCategoryMenu={catMenu}
                    goalProgressFor={(c) =>
                        groups.find((g) => g.id === c.groupId)?.kind === "goal"
                            ? goalProgress(c, snapshot.budgets, todayYear, todayMonth)
                            : null
                    }
                />
            )}

            {dialog?.type === "edit" && (
                <CategoryEditDialog
                    category={dialog.category}
                    groups={groups}
                    onClose={() => setDialog(null)}
                />
            )}
            {dialog?.type === "delete" && (
                <CategoryDeleteDialog
                    category={dialog.category}
                    categories={snapshot.categories}
                    txCount={txCountByCat.get(dialog.category.id) ?? 0}
                    onClose={() => setDialog(null)}
                />
            )}
            {dialog?.type === "distribute" && (
                <DistributeGoalDialog
                    goal={dialog.category}
                    budgets={snapshot.budgets}
                    startYear={year}
                    startMonth={mode === "month" ? month + 1 : now.getMonth() + 1}
                    setBudgets={setBudgets}
                    notify={notify}
                    onClose={() => setDialog(null)}
                />
            )}
        </div>
    );
}

function GoalUrgency({ goal, funded }) {
    if (!goal.goalTargetDate || funded >= goal.goalTarget) return null;
    const days = Math.ceil((new Date(`${goal.goalTargetDate}T23:59:59`) - new Date()) / 86_400_000);
    if (days > 60) return null;
    const overdue = days < 0;
    return (
        <span className={`goal-urgency ${overdue ? "goal-urgency_overdue" : ""}`}>
            {overdue ? " · overdue" : ` · 🔥 ${days}d left`}
        </span>
    );
}

function DistributeGoalDialog({
    goal,
    budgets,
    startYear,
    startMonth,
    setBudgets,
    notify,
    onClose,
}) {
    const suggestedMonths = (() => {
        if (!goal.goalTargetDate) return "";
        const match = /^(\d{4})-(\d{2})/.exec(goal.goalTargetDate);
        if (!match) return "";
        const count = (+match[1] - startYear) * 12 + (+match[2] - startMonth) + 1;
        return String(Math.max(1, Math.min(120, count)));
    })();
    const [months, setMonths] = useState(suggestedMonths);
    const [busy, setBusy] = useState(false);
    const count = Number.parseInt(months, 10);
    const apply = async () => {
        if (!(count > 0 && count <= 120 && goal.goalTarget > 0)) return;
        setBusy(true);
        try {
            const before = budgets.reduce((sum, b) => {
                if (b.categoryId !== goal.id) return sum;
                if (b.year < startYear || (b.year === startYear && b.month < startMonth)) {
                    return sum + b.amount;
                }
                return sum;
            }, 0);
            const remaining = Math.max(0, goal.goalTarget - before);
            const base = Math.floor(remaining / count);
            const remainder = remaining - base * count;
            const cells = Array.from({ length: count }, (_, i) => {
                const offset = startMonth - 1 + i;
                return {
                    categoryId: goal.id,
                    year: startYear + Math.floor(offset / 12),
                    month: (offset % 12) + 1,
                    amount: base + (i < remainder ? 1 : 0),
                };
            });
            const planned = new Set(cells.map((c) => `${c.year}-${c.month}`));
            for (const b of budgets) {
                const future =
                    b.categoryId === goal.id &&
                    (b.year > startYear || (b.year === startYear && b.month >= startMonth));
                if (future && !planned.has(`${b.year}-${b.month}`)) cells.push({ ...b, amount: 0 });
            }
            await setBudgets(cells);
            onClose();
        } catch (e) {
            notify({ title: "Failed to distribute goal", content: String(e), theme: "danger" });
        } finally {
            setBusy(false);
        }
    };
    return (
        <AppDialog
            title={`Distribute ${goal.name}`}
            onClose={onClose}
            onApply={apply}
            applyText="Distribute"
            applyLoading={busy}
            applyDisabled={!(count > 0 && count <= 120 && goal.goalTarget > 0)}
        >
            <div className="goal-distribute-prompt">Number of months</div>
            <FTextInput
                type="number"
                min={1}
                max={120}
                value={months}
                onChange={(e) => setMonths(e.target.value)}
                placeholder="For example, 6"
                autoFocus
            />
        </AppDialog>
    );
}
