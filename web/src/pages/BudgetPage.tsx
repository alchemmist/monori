import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ActionIcon, Button, SegmentedControl } from "@mantine/core";
import InlineSelect from "../ui/InlineSelect.jsx";
import RowMenu from "../ui/RowMenu.jsx";
import { Plus, ChevronDown, EllipsisVertical } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { orderedGroups, categoriesByGroup } from "../categoryOrder.js";
import { MONTHS_SHORT, MONTHS, normalizeKop, rub } from "../format.js";
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
import type { BudgetYearResult } from "../engine/budget.js";
import type { BudgetCell as BudgetCellModel, Category, Id, ToastMessage } from "../types.js";
import type { RowMenuItem } from "../ui/RowMenu.js";

const YEAR_DENSITY: Record<string, Array<"budgeted" | "activity" | "balance">> = {
    full: ["budgeted", "activity", "balance"],
    plan: ["budgeted"],
    actual: ["activity", "balance"],
};

type Density = keyof typeof YEAR_DENSITY;
type BudgetDialog =
    | { type: "edit"; category: Partial<Category> & Pick<Category, "groupId"> }
    | { type: "delete" | "distribute"; category: Category };
type SelectedBudgetCell = Omit<BudgetCellModel, "amount">;
type GoalStyle = CSSProperties & { "--goal-progress"?: string };

export default function BudgetPage({
    results,
    firstYear,
    lastYear,
}: {
    results: Map<number, BudgetYearResult>;
    firstYear: number;
    lastYear: number;
}) {
    const {
        snapshot,
        setBudget,
        setBudgets,
        copyBudgetYear,
        fillBudgetForward,
        archiveGoal,
        patchCategory,
        notify,
    } = useStore();
    if (!snapshot) throw new Error("budget page requires a loaded snapshot");
    const now = new Date();
    const todayYear = now.getFullYear();
    const todayMonth = now.getMonth() + 1;
    const [year, setYear] = useState(now.getFullYear());
    const [month, setMonth] = useState(now.getMonth()); // 0-based
    const [mode, setMode] = useState<"year" | "month">("year");
    const [density, setDensity] = useState<Density>("full");
    const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});
    const [showUnused, setShowUnused] = useState(false);
    const [dialog, setDialog] = useState<BudgetDialog | null>(null);
    const [selectedBudgetCell, setSelectedBudgetCell] = useState<SelectedBudgetCell | null>(null);
    const [fillingForward, setFillingForward] = useState(false);
    // 0-based index of the month whose Available just hit zero, or -1. The
    // celebration is transient: it plays and then clears itself after the sweep.
    const [completeMonth, setCompleteMonth] = useState(-1);
    const celebrateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [creatingYear, setCreatingYear] = useState(false);

    const res = results.get(year);
    if (!res) throw new Error(`budget result for ${year} is missing`);
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
        const used = (c: Category) =>
            (res.byCategory.get(c.id) ?? []).some(
                (m) =>
                    normalizeKop(m.budgeted) !== 0 ||
                    normalizeKop(m.outflows) !== 0 ||
                    normalizeKop(m.balance) !== 0,
            );
        let unused = 0;
        const filtered = new Map<Id, Category[]>();
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
    const canCreateYear = year === lastYear && year > 2000 && year <= 2100;
    const hasUnused = unusedCount > 0;

    const txCountByCat = useMemo(() => {
        const m = new Map<Id, number>();
        for (const t of effectiveTransactions(snapshot.transactions)) {
            if (t.categoryId != null) m.set(t.categoryId, (m.get(t.categoryId) ?? 0) + 1);
        }
        return m;
    }, [snapshot.transactions]);

    const years: number[] = [];
    for (let y = firstYear; y <= lastYear; y++) years.push(y);

    const available = res.available[month]!;
    const overspent = res.overspent[month]!;
    const income = res.income[month]!;
    const budgetedTotal = res.budgetedTotal[month]!;

    // any navigation cancels an in-flight celebration
    useEffect(() => {
        if (celebrateTimer.current) clearTimeout(celebrateTimer.current);
        setCompleteMonth(-1);
    }, [year, month, mode]);

    useEffect(
        () => () => {
            if (celebrateTimer.current) clearTimeout(celebrateTimer.current);
        },
        [],
    );

    const saveBudget = (
        categoryId: Id,
        targetYear: number,
        targetMonth: number,
        amount: number,
    ) => {
        const target = results.get(targetYear);
        const previous = normalizeKop(
            target?.byCategory.get(categoryId)?.[targetMonth - 1]?.budgeted ?? 0,
        );
        const delta = amount - previous;
        // celebrate whichever month this edit drives to exactly zero — any month,
        // not only the current or the one on screen
        const before = normalizeKop(target?.available[targetMonth - 1] ?? 0);
        const after = normalizeKop(before - delta);
        const hitsZero = before !== 0 && after === 0;
        void setBudget(categoryId, targetYear, targetMonth, amount);
        if (targetYear === year && hitsZero) {
            setCompleteMonth(targetMonth - 1);
            if (celebrateTimer.current) clearTimeout(celebrateTimer.current);
            celebrateTimer.current = setTimeout(() => setCompleteMonth(-1), 1100);
        }
    };

    const catMenu = (c: Category): RowMenuItem[] => {
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
                                  type: (c.goalTarget ?? 0) > 0 ? "distribute" : "edit",
                                  category: c,
                              }),
                          text:
                              (c.goalTarget ?? 0) > 0
                                  ? "Distribute across months"
                                  : "Set target first",
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
    const canFillForward = Boolean(
        selectedBudgetCell && selectedBudgetCell.month < 12 && selectedCategory,
    );

    const fillForward = async () => {
        if (!canFillForward || !selectedBudgetCell || !selectedCategory) return;
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

    const createNextYear = async () => {
        const sourceYear = year - 1;
        setCreatingYear(true);
        try {
            const count = await copyBudgetYear(sourceYear, year);
            notify({
                title: `${year} budget created`,
                content: `${count} budget cell${count === 1 ? "" : "s"} copied from ${sourceYear}`,
                theme: "success",
            });
        } catch (e) {
            notify({ title: "Failed to create budget year", content: String(e), theme: "danger" });
        } finally {
            setCreatingYear(false);
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
                <Button
                    className={`budget-toolbar__create ${canCreateYear ? "" : "budget-toolbar__action_hidden"}`}
                    size="xs"
                    variant="light"
                    loading={creatingYear}
                    onClick={() => void createNextYear()}
                    disabled={!canCreateYear}
                    aria-hidden={!canCreateYear}
                    tabIndex={canCreateYear ? 0 : -1}
                >
                    Create {year}
                </Button>
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
                {selectedBudgetCell && selectedCategory && selectedBudgetCell.month < 12 && (
                    <Button
                        size="xs"
                        variant="light"
                        loading={fillingForward}
                        onClick={() => void fillForward()}
                        title={`Replace ${selectedCategory.name}'s remaining ${selectedBudgetCell.year} budgets with this value`}
                    >
                        Fill {selectedCategory.name} to Dec
                    </Button>
                )}
                <Button
                    className={`budget-toolbar__unused ${hasUnused ? "" : "budget-toolbar__action_hidden"}`}
                    size="xs"
                    variant="subtle"
                    onClick={() => setShowUnused((v) => !v)}
                    title="Categories with nothing budgeted, spent or held this year"
                    disabled={!hasUnused}
                    aria-hidden={!hasUnused}
                    tabIndex={hasUnused ? 0 : -1}
                >
                    {showUnused ? "Hide unused" : `Show ${unusedCount} unused`}
                </Button>
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
                            className={`card hero-card hero-card_available ${completeMonth === month ? "hero-card_complete" : ""}`}
                        >
                            <div className="hero-card__label">Available to budget</div>
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
                                                setCollapsed({
                                                    ...collapsed,
                                                    [g.id]: isCollapsed !== true,
                                                })
                                            }
                                        >
                                            <td>
                                                <span
                                                    className={`group-row__chevron ${isCollapsed === true ? "group-row__chevron_collapsed" : ""}`}
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
                                        isCollapsed !== true &&
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
                                                                    ? ({
                                                                          "--goal-progress": `${progress.percent}%`,
                                                                      } as GoalStyle)
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
                    completeMonth={completeMonth}
                    cols={YEAR_DENSITY[density]!}
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

function GoalUrgency({ goal, funded }: { goal: Category; funded: number }) {
    if (
        goal.goalTargetDate == null ||
        goal.goalTargetDate === "" ||
        funded >= (goal.goalTarget ?? 0)
    )
        return null;
    const days = Math.ceil(
        (new Date(`${goal.goalTargetDate}T23:59:59`).getTime() - Date.now()) / 86_400_000,
    );
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
}: {
    goal: Category;
    budgets: BudgetCellModel[];
    startYear: number;
    startMonth: number;
    setBudgets: (cells: BudgetCellModel[]) => Promise<void>;
    notify: (toast: ToastMessage) => void;
    onClose: () => void;
}) {
    const suggestedMonths = (() => {
        if (goal.goalTargetDate == null || goal.goalTargetDate === "") return "";
        const match = /^(\d{4})-(\d{2})/.exec(goal.goalTargetDate);
        if (!match) return "";
        const count = (+match[1]! - startYear) * 12 + (+match[2]! - startMonth) + 1;
        return String(Math.max(1, Math.min(120, count)));
    })();
    const [months, setMonths] = useState(suggestedMonths);
    const [busy, setBusy] = useState(false);
    const count = Number.parseInt(months, 10);
    const apply = async () => {
        if (!(count > 0 && count <= 120 && (goal.goalTarget ?? 0) > 0)) return;
        setBusy(true);
        try {
            const before = budgets.reduce((sum, b) => {
                if (b.categoryId !== goal.id) return sum;
                if (b.year < startYear || (b.year === startYear && b.month < startMonth)) {
                    return sum + b.amount;
                }
                return sum;
            }, 0);
            const remaining = Math.max(0, (goal.goalTarget ?? 0) - before);
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
            onApply={() => void apply()}
            applyText="Distribute"
            applyLoading={busy}
            applyDisabled={!(count > 0 && count <= 120 && (goal.goalTarget ?? 0) > 0)}
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
