import { useMemo, useState } from "react";
import { Button, DropdownMenu, SegmentedRadioGroup, Select } from "@gravity-ui/uikit";
import { Plus, ChevronDown, EllipsisVertical } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { MONTHS_SHORT, MONTHS, rub } from "../format.js";
import BudgetCell from "../components/BudgetCell.jsx";
import { Money, BalancePill } from "../components/Money.jsx";
import { CategoryEditDialog, CategoryDeleteDialog } from "../components/CategoryDialogs.jsx";
import "./budget.css";

export default function BudgetPage({ results, firstYear, lastYear }) {
  const { snapshot, setBudget } = useStore();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth()); // 0-based
  const [mode, setMode] = useState("month");
  const [collapsed, setCollapsed] = useState({});
  const [dialog, setDialog] = useState(null); // {type: 'edit'|'delete'|'new', category}

  const res = results.get(year);
  const groups = useMemo(
    () => snapshot.groups.filter((g) => g.kind === "expense"),
    [snapshot.groups]
  );
  const catsByGroup = useMemo(() => {
    const m = new Map(groups.map((g) => [g.id, []]));
    for (const c of snapshot.categories) {
      if (m.has(c.groupId)) m.get(c.groupId).push(c);
    }
    return m;
  }, [snapshot.categories, groups]);

  const txCountByCat = useMemo(() => {
    const m = new Map();
    for (const t of snapshot.transactions) {
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

  const catMenu = (c) => [
    { action: () => setDialog({ type: "edit", category: c }), text: "Edit" },
    {
      action: () => setDialog({ type: "delete", category: c }),
      text: "Delete",
      theme: "danger",
    },
  ];

  return (
    <div className="fade-in">
      <div className="budget-toolbar">
        <h1 className="page-title" style={{ margin: 0 }}>
          Budget
        </h1>
        <Select
          value={[String(year)]}
          onUpdate={(v) => setYear(+v[0])}
          options={years.map((y) => ({ value: String(y), content: String(y) }))}
          size="m"
        />
        {mode === "month" && (
          <SegmentedRadioGroup
            size="m"
            value={String(month)}
            onUpdate={(v) => setMonth(+v)}
            options={MONTHS_SHORT.map((m, i) => ({ value: String(i), content: m }))}
          />
        )}
        <div style={{ flex: 1 }} />
        <SegmentedRadioGroup
          size="m"
          value={mode}
          onUpdate={setMode}
          options={[
            { value: "month", content: "Month" },
            { value: "matrix", content: "Year matrix" },
          ]}
        />
      </div>

      {mode === "month" && (
        <>
          <div className="budget-hero">
            <div className="card hero-card">
              <div className="hero-card__label">Available to budget</div>
              <div
                className="hero-card__value num"
                style={{ color: available < 0 ? "var(--m-expense)" : "var(--m-income)" }}
              >
                {rub(available)} ₽
              </div>
              <div className="hero-card__hint">end of {MONTHS[month]}</div>
            </div>
            <div className="card hero-card">
              <div className="hero-card__label">Income</div>
              <div className="hero-card__value num">{rub(income)} ₽</div>
              <div className="hero-card__hint">{MONTHS[month]} {year}</div>
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
                style={{ color: overspent < 0 ? "var(--m-expense)" : "var(--m-text-faint)" }}
              >
                {rub(overspent)} ₽
              </div>
              <div className="hero-card__hint">uncovered this month</div>
            </div>
          </div>

          <div className="card" style={{ overflow: "hidden" }}>
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
                  let gb = 0, go = 0, gbal = 0;
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
                      onClick={() => setCollapsed({ ...collapsed, [g.id]: !isCollapsed })}
                    >
                      <td>
                        <span
                          className={`group-row__chevron ${isCollapsed ? "group-row__chevron_collapsed" : ""}`}
                        >
                          <ChevronDown width={14} height={14} />
                        </span>
                        {g.name}
                        <span className="group-row__count">{cats.length}</span>
                        <Button
                          size="xs"
                          view="flat-secondary"
                          style={{ marginLeft: 8 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDialog({ type: "edit", category: { groupId: g.id } });
                          }}
                        >
                          <Plus width={12} height={12} />
                        </Button>
                      </td>
                      <td><Money value={gb} /></td>
                      <td><Money value={go} signColor /></td>
                      <td><Money value={gbal} /></td>
                      <td />
                    </tr>,
                    !isCollapsed &&
                      cats.map((c) => {
                        const m = res.byCategory.get(c.id)?.[month] ?? {
                          budgeted: 0,
                          outflows: 0,
                          balance: 0,
                        };
                        const spentRatio =
                          m.budgeted > 0 ? Math.min(1, -m.outflows / m.budgeted) : m.outflows < 0 ? 1 : 0;
                        return (
                          <tr key={c.id} className="cat-row">
                            <td>
                              <span className="cat-row__name">
                                {c.name}
                                <span className="cat-progress">
                                  <span
                                    className="cat-progress__fill"
                                    style={{
                                      width: `${spentRatio * 100}%`,
                                      background:
                                        m.balance < 0 ? "var(--m-expense)" : "var(--m-accent)",
                                    }}
                                  />
                                </span>
                              </span>
                            </td>
                            <td>
                              <BudgetCell
                                value={m.budgeted}
                                onChange={(v) => setBudget(c.id, year, month + 1, v)}
                              />
                            </td>
                            <td><Money value={m.outflows} signColor /></td>
                            <td><BalancePill value={m.balance} /></td>
                            <td>
                              <span className="cat-row__menu" onClick={(e) => e.stopPropagation()}>
                                <DropdownMenu
                                  renderSwitcher={(props) => (
                                    <Button {...props} size="xs" view="flat-secondary">
                                      <EllipsisVertical width={14} height={14} />
                                    </Button>
                                  )}
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

      {mode === "matrix" && (
        <div className="card matrix-wrap matrix">
          <table className="budget-grid">
            <thead>
              <tr>
                <th>Category</th>
                {MONTHS_SHORT.map((m) => (
                  <th key={m}>{m}</th>
                ))}
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => {
                const cats = catsByGroup.get(g.id) ?? [];
                return [
                  <tr key={`g${g.id}`} className="group-row">
                    <td colSpan={14}>{g.name}</td>
                  </tr>,
                  cats.map((c) => {
                    const months = res.byCategory.get(c.id) ?? [];
                    const total = months.reduce((s, m) => s + m.budgeted, 0);
                    return (
                      <tr key={c.id} className="cat-row">
                        <td>{c.name}</td>
                        {MONTHS_SHORT.map((_, i) => (
                          <td key={i}>
                            <BudgetCell
                              value={months[i]?.budgeted ?? 0}
                              onChange={(v) => setBudget(c.id, year, i + 1, v)}
                            />
                          </td>
                        ))}
                        <td><Money value={total} /></td>
                      </tr>
                    );
                  }),
                ];
              })}
            </tbody>
          </table>
        </div>
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
    </div>
  );
}
