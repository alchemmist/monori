import { useMemo, useState } from "react";
import { ChartBoundary } from "../components/ChartCard.jsx";
import TimeNavigator from "../components/TimeNavigator.jsx";
import { Button, Select } from "@gravity-ui/uikit";
import { useStore } from "../store.js";
import { rub, moneyCompact, MONTHS_SHORT } from "../format.js";
import "./dashboard.css";

const PRESETS = [
  { id: "6m", label: "6m", months: 6 },
  { id: "1y", label: "1y", months: 12 },
  { id: "3y", label: "3y", months: 36 },
  { id: "5y", label: "5y", months: 60 },
  { id: "ytd", label: "YTD" },
  { id: "all", label: "All" },
];

import { C, axisCommon } from "./chartTheme.js";

/** Analytics count "To be Budgeted" as real inflow (it holds actual money
 * injections). Internal transfers are uncategorized and thus excluded. */
export default function DashboardPage({ results, firstYear, lastYear }) {
  const { snapshot } = useStore();
  const now = new Date();
  const [donutYear, setDonutYear] = useState(String(now.getFullYear()));
  const [drillCat, setDrillCat] = useState(
    () => String(snapshot.categories.find((c) => c.name === "Groceries")?.id ?? "")
  );
  const [drillYear, setDrillYear] = useState(String(now.getFullYear()));
  const [stackYear, setStackYear] = useState(String(now.getFullYear()));
  const [catStackYear, setCatStackYear] = useState(String(now.getFullYear()));

  const excludedIds = useMemo(() => new Set(), []);
  const incomeGroupIds = useMemo(
    () => new Set(snapshot.groups.filter((g) => g.kind === "income").map((g) => g.id)),
    [snapshot.groups]
  );
  const catById = useMemo(
    () => new Map(snapshot.categories.map((c) => [c.id, c])),
    [snapshot.categories]
  );

  // Monthly series over full history: real income / expenses (kopecks, positive numbers)
  const monthly = useMemo(() => {
    const map = new Map(); // 'y-m' -> {income, expense}
    for (const t of snapshot.transactions) {
      if (t.categoryId == null || excludedIds.has(t.categoryId)) continue;
      const cat = catById.get(t.categoryId);
      if (!cat) continue;
      const key = t.date.slice(0, 7);
      let e = map.get(key);
      if (!e) map.set(key, (e = { income: 0, expense: 0 }));
      if (incomeGroupIds.has(cat.groupId)) e.income += t.amount;
      else e.expense += -t.amount;
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [snapshot.transactions, excludedIds, incomeGroupIds, catById]);

  const nowKey = now.toISOString().slice(0, 7);
  const closed = monthly.filter(([k]) => k < nowKey); // full months only
  const last12 = closed.slice(-12);

  // Time window over `closed` for the trend chart: [loIdx, hiIdx] inclusive.
  const [trendRange, setTrendRange] = useState(null); // null = default 3y
  const presetRange = (id) => {
    const n = closed.length;
    if (n === 0) return [0, 0];
    if (id === "all") return [0, n - 1];
    if (id === "ytd") {
      const i = closed.findIndex(([k]) => k.startsWith(String(now.getFullYear())));
      return [i === -1 ? Math.max(0, n - 1) : i, n - 1];
    }
    const m = PRESETS.find((p) => p.id === id).months;
    return [Math.max(0, n - m), n - 1];
  };
  const [trendLo, trendHi] = trendRange ?? presetRange("3y");
  const activePreset = PRESETS.find((p) => {
    const [a, b] = presetRange(p.id);
    return a === trendLo && b === trendHi;
  })?.id;

  const kpis = useMemo(() => {
    const ytd = monthly.filter(([k]) => k.startsWith(String(now.getFullYear())));
    const netYtd = ytd.reduce((s, [, v]) => s + v.income - v.expense, 0);
    const inc12 = last12.reduce((s, [, v]) => s + v.income, 0);
    const exp12 = last12.reduce((s, [, v]) => s + v.expense, 0);
    const savingsRate = inc12 > 0 ? ((inc12 - exp12) / inc12) * 100 : 0;
    const cur = monthly.find(([k]) => k === nowKey)?.[1] ?? { income: 0, expense: 0 };
    const day = now.getDate();
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const dailyRate = cur.expense / day;
    const forecast = dailyRate * daysInMonth;
    const prevKey = `${now.getFullYear() - (now.getMonth() === 0 ? 1 : 0)}-${String(now.getMonth() === 0 ? 12 : now.getMonth()).padStart(2, "0")}`;
    const prev = monthly.find(([k]) => k === prevKey)?.[1] ?? { income: 0, expense: 0 };
    const saved12 = inc12 - exp12;
    const totalNet = monthly.reduce((s, [, v]) => s + v.income - v.expense, 0);
    const exp12avg = exp12 / Math.max(last12.length, 1);
    const runway = exp12avg > 0 ? totalNet / exp12avg : null;
    return { netYtd, savingsRate, exp12avg, cur, dailyRate, forecast, prev, saved12, runway };
  }, [monthly, last12, nowKey, now]);

  // Chart 1: income/expense bars + savings rate line over the selected window
  const trendData = useMemo(() => {
    const rows = closed.slice(trendLo, trendHi + 1);
    return {
      xAxis: { type: "category", categories: rows.map(([k]) => k), ...axisCommon },
      yAxis: [
        { labels: { ...axisCommon.labels, formatter: undefined }, ...axisCommon },
        { labels: axisCommon.labels, lineColor: "transparent", gridColor: "transparent", maxPadding: 0.05 },
      ],
      legend: { enabled: true, itemStyle: { fontColor: "var(--m-text-dim)", fontSize: "12px" } },
      series: { data: [
        {
          type: "bar-x", name: "Income", color: C.income,
          data: rows.map(([k, v]) => ({ x: k, y: v.income / 100 })),
        },
        {
          type: "bar-x", name: "Expenses", color: C.expense,
          data: rows.map(([k, v]) => ({ x: k, y: v.expense / 100 })),
        },
        {
          type: "line", name: "Savings rate %", color: C.accent, yAxis: 1, lineWidth: 1.5,
          // 1-2-1 weighted moving average: the lib draws straight polylines only,
          // smoothing the data is what keeps this line from looking like a saw
          data: rows.map(([k], i) => {
            const rate = (j) => {
              const v = rows[Math.max(0, Math.min(rows.length - 1, j))][1];
              return v.income > 0
                ? Math.max(-100, Math.min(100, ((v.income - v.expense) / v.income) * 100))
                : null;
            };
            const [a, b, c] = [rate(i - 1), rate(i), rate(i + 1)];
            if (b == null) return { x: k, y: null };
            const parts = [[a, 1], [b, 2], [c, 1]].filter(([v]) => v != null);
            const w = parts.reduce((s, [, ww]) => s + ww, 0);
            return { x: k, y: Math.round(parts.reduce((s, [v, ww]) => s + v * ww, 0) / w) };
          }),
        },
      ] },
      chart: {
        margin: { top: 10, right: 10, bottom: 0, left: 10 },
        zoom: { enabled: true, type: "x" },
      },
      tooltip: { enabled: true },
    };
  }, [closed, trendLo, trendHi]);

  // Chart 2: donut by category for a year
  const donutData = useMemo(() => {
    const sums = new Map();
    for (const t of snapshot.transactions) {
      if (!t.date.startsWith(donutYear) || t.categoryId == null) continue;
      const cat = catById.get(t.categoryId);
      if (!cat || incomeGroupIds.has(cat.groupId) || excludedIds.has(t.categoryId)) continue;
      if (t.amount >= 0) continue;
      sums.set(cat.name, (sums.get(cat.name) ?? 0) - t.amount);
    }
    const sorted = [...sums.entries()].sort((a, b) => b[1] - a[1]);
    const top = sorted.slice(0, 11);
    const rest = sorted.slice(11).reduce((s, [, v]) => s + v, 0);
    if (rest > 0) top.push(["Other", rest]);
    return {
      legend: { enabled: true, itemStyle: { fontColor: "var(--m-text-dim)", fontSize: "12px" } },
      series: { data: [
        {
          type: "pie",
          innerRadius: "62%",
          borderColor: "var(--m-surface)",
          borderWidth: 2,
          dataLabels: { enabled: false },
          data: top.map(([name, v], i) => ({
            name,
            value: Math.round(v / 100),
            color: C.palette[i % C.palette.length],
          })),
        },
      ] },
      tooltip: { enabled: true },
    };
  }, [snapshot.transactions, donutYear, catById, incomeGroupIds, excludedIds]);

  // Chart 3: selected category by month for a year
  const drillData = useMemo(() => {
    const catId = drillCat ? +drillCat : null;
    const sums = Array(12).fill(0);
    if (catId != null) {
      for (const t of snapshot.transactions) {
        if (t.categoryId !== catId || !t.date.startsWith(drillYear)) continue;
        sums[+t.date.slice(5, 7) - 1] += Math.abs(t.amount);
      }
    }
    return {
      xAxis: { type: "category", categories: MONTHS_SHORT, ...axisCommon },
      yAxis: [{ labels: axisCommon.labels, ...axisCommon }],
      legend: { enabled: false },
      series: { data: [
        {
          type: "bar-x",
          name: catId != null ? catById.get(catId)?.name : "",
          color: C.accent,
          data: sums.map((v, i) => ({ x: i, y: v / 100 })),
        },
      ] },
      tooltip: { enabled: true },
    };
  }, [snapshot.transactions, drillCat, drillYear, catById]);

  // Chart 4: cumulative net over all history
  const cumulativeData = useMemo(() => {
    let acc = 0;
    const pts = monthly.map(([k, v]) => {
      acc += v.income - v.expense;
      return { x: k, y: Math.round(acc / 100) };
    });
    return {
      xAxis: { type: "category", categories: pts.map((p) => p.x), ...axisCommon },
      yAxis: [{ labels: axisCommon.labels, ...axisCommon }],
      legend: { enabled: false },
      series: { data: [
        {
          type: "area", name: "Cumulative net", color: C.income,
          lineWidth: 2, opacity: 0.25,
          data: pts,
        },
      ] },
      chart: { zoom: { enabled: true, type: "x" } },
      tooltip: { enabled: true },
    };
  }, [monthly]);

  // Chart 5: expense structure by group, stacked, its own year selector
  const groupStackData = useMemo(() => {
    const expenseGroups = snapshot.groups.filter((g) => g.kind === "expense");
    const perGroup = new Map(expenseGroups.map((g) => [g.id, Array(12).fill(0)]));
    for (const t of snapshot.transactions) {
      if (!t.date.startsWith(stackYear) || t.categoryId == null || t.amount >= 0) continue;
      const cat = catById.get(t.categoryId);
      if (!cat || !perGroup.has(cat.groupId) || excludedIds.has(t.categoryId)) continue;
      perGroup.get(cat.groupId)[+t.date.slice(5, 7) - 1] -= t.amount;
    }
    return {
      xAxis: { type: "category", categories: MONTHS_SHORT, ...axisCommon },
      yAxis: [{ labels: axisCommon.labels, ...axisCommon }],
      legend: { enabled: true, itemStyle: { fontColor: "var(--m-text-dim)", fontSize: "12px" } },
      series: { data: expenseGroups.map((g, i) => ({
        type: "bar-x",
        stacking: "normal",
        name: g.name,
        color: C.palette[i % C.palette.length],
        data: perGroup.get(g.id).map((v, m) => ({ x: m, y: Math.round(v / 100) })),
      })) },
      tooltip: { enabled: true },
    };
  }, [snapshot.transactions, snapshot.groups, stackYear, catById, excludedIds]);

  // Spending by category, stacked by month — same top-N categories (and thus
  // colors) as the donut, so the two views line up.
  const catStackData = useMemo(() => {
    const perCat = new Map(); // name -> Array(12) monthly outflow totals
    for (const t of snapshot.transactions) {
      if (!t.date.startsWith(catStackYear) || t.categoryId == null || t.amount >= 0) continue;
      const cat = catById.get(t.categoryId);
      if (!cat || incomeGroupIds.has(cat.groupId) || excludedIds.has(t.categoryId)) continue;
      let arr = perCat.get(cat.name);
      if (!arr) perCat.set(cat.name, (arr = Array(12).fill(0)));
      arr[+t.date.slice(5, 7) - 1] -= t.amount;
    }
    const rows = [...perCat.entries()]
      .map(([name, arr]) => ({ name, arr, total: arr.reduce((s, v) => s + v, 0) }))
      .sort((a, b) => b.total - a.total);
    const top = rows.slice(0, 11);
    const rest = rows.slice(11);
    const series = top.map((r, i) => ({
      type: "bar-x",
      stacking: "normal",
      name: r.name,
      color: C.palette[i % C.palette.length],
      data: r.arr.map((v, m) => ({ x: m, y: Math.round(v / 100) })),
    }));
    if (rest.length) {
      const other = Array(12).fill(0);
      for (const r of rest) r.arr.forEach((v, m) => (other[m] += v));
      series.push({
        type: "bar-x",
        stacking: "normal",
        name: "Other",
        color: C.palette[11 % C.palette.length],
        data: other.map((v, m) => ({ x: m, y: Math.round(v / 100) })),
      });
    }
    return {
      xAxis: { type: "category", categories: MONTHS_SHORT, ...axisCommon },
      yAxis: [{ labels: axisCommon.labels, ...axisCommon }],
      legend: { enabled: true, itemStyle: { fontColor: "var(--m-text-dim)", fontSize: "12px" } },
      series: { data: series },
      tooltip: { enabled: true },
    };
  }, [snapshot.transactions, catStackYear, catById, incomeGroupIds, excludedIds]);

  const years = [];
  for (let y = firstYear; y <= Math.min(lastYear, now.getFullYear()); y++) years.push(String(y));

  const expenseCatOptions = snapshot.categories
    .filter((c) => !incomeGroupIds.has(c.groupId))
    .map((c) => ({ value: String(c.id), content: c.name }));

  return (
    <div className="fade-in">
      <h1 className="page-title">Dashboard</h1>

      <div className="kpi-row">
        <Kpi label="Net year to date" value={`${rub(kpis.netYtd)} ₽`}
          color={kpis.netYtd >= 0 ? "var(--m-income)" : "var(--m-expense)"} sub={`${now.getFullYear()}`} />
        <Kpi label="Savings rate" value={`${kpis.savingsRate.toFixed(0)}%`}
          color={kpis.savingsRate >= 0 ? "var(--m-income)" : "var(--m-expense)"} sub="last 12 months" />
        <Kpi label="Avg monthly spend" value={`${rub(kpis.exp12avg)} ₽`} sub="last 12 months" />
        <Kpi label="Spent this month" value={`${rub(kpis.cur.expense)} ₽`}
          sub={`vs ${rub(kpis.prev.expense)} ₽ last month`} />
        <Kpi label="Daily rate" value={`${rub(kpis.dailyRate)} ₽`} sub="this month, per day" />
        <Kpi label="Month forecast" value={`${rub(kpis.forecast)} ₽`}
          color={kpis.forecast > kpis.exp12avg ? "var(--m-warning)" : "var(--m-income)"} sub="at current pace" />
        <Kpi label="Saved" value={`${rub(kpis.saved12)} ₽`}
          color={kpis.saved12 >= 0 ? "var(--m-income)" : "var(--m-expense)"} sub="last 12 months" />
        <Kpi label="Runway" value={kpis.runway != null ? `${kpis.runway.toFixed(1)} mo` : "—"}
          color={kpis.runway != null && kpis.runway < 3 ? "var(--m-warning)" : undefined}
          sub="all-time net ÷ avg monthly spend" />
      </div>

      <div className="charts-grid">
        <div className="card chart-card chart-card_wide">
          <div className="chart-card__head">
            <div className="chart-card__title">
              Income vs expenses · {fmtMonthKey(closed[trendLo]?.[0])} — {fmtMonthKey(closed[trendHi]?.[0])}
              <span className="chart-card__hint"> · {trendHi - trendLo + 1} months · drag to zoom</span>
            </div>
            <div className="preset-row">
              {PRESETS.map((p) => (
                <Button
                  key={p.id}
                  size="s"
                  view={activePreset === p.id ? "normal" : "flat-secondary"}
                  selected={activePreset === p.id}
                  onClick={() => setTrendRange(presetRange(p.id))}
                >
                  {p.label}
                </Button>
              ))}
            </div>
          </div>
          <div className="chart-card__body chart-card__body_tall">
            <ChartBoundary data={trendData} />
          </div>
          <TimeNavigator
            items={closed.map(([k, v]) => ({ key: k, value: v.expense }))}
            range={[trendLo, trendHi]}
            onChange={setTrendRange}
          />
        </div>

        <div className="card chart-card">
          <div className="chart-card__head">
            <div className="chart-card__title">Spending by category</div>
            <Select size="s" value={[donutYear]} onUpdate={(v) => setDonutYear(v[0])}
              options={years.map((y) => ({ value: y, content: y }))} />
          </div>
          <div className="chart-card__body">
            <ChartBoundary data={donutData} />
          </div>
        </div>

        <div className="card chart-card">
          <div className="chart-card__head">
            <div className="chart-card__title">Category by month</div>
            <div style={{ display: "flex", gap: 8 }}>
              <Select size="s" filterable placeholder="Category"
                value={drillCat ? [drillCat] : []}
                onUpdate={(v) => setDrillCat(v[0] ?? "")}
                options={expenseCatOptions} />
              <Select size="s" value={[drillYear]} onUpdate={(v) => setDrillYear(v[0])}
                options={years.map((y) => ({ value: y, content: y }))} />
            </div>
          </div>
          <div className="chart-card__body">
            {drillCat ? (
              <ChartBoundary data={drillData} />
            ) : (
              <div style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--m-text-faint)" }}>
                Pick a category to see its monthly spending
              </div>
            )}
          </div>
        </div>

        <div className="card chart-card chart-card_wide">
          <div className="chart-card__head">
            <div className="chart-card__title">Spending by category · by month</div>
            <Select size="s" value={[catStackYear]} onUpdate={(v) => setCatStackYear(v[0])}
              options={years.map((y) => ({ value: y, content: y }))} />
          </div>
          <div className="chart-card__body">
            <ChartBoundary data={catStackData} />
          </div>
        </div>

        <div className="card chart-card">
          <div className="chart-card__head">
            <div className="chart-card__title">Cumulative net · all time</div>
          </div>
          <div className="chart-card__body">
            <ChartBoundary data={cumulativeData} />
          </div>
        </div>

        <div className="card chart-card">
          <div className="chart-card__head">
            <div className="chart-card__title">Expense structure by group</div>
            <Select size="s" value={[stackYear]} onUpdate={(v) => setStackYear(v[0])}
              options={years.map((y) => ({ value: y, content: y }))} />
          </div>
          <div className="chart-card__body">
            <ChartBoundary data={groupStackData} />
          </div>
        </div>
      </div>
    </div>
  );
}

function fmtMonthKey(key) {
  if (!key) return "";
  return `${MONTHS_SHORT[+key.slice(5, 7) - 1]} ${key.slice(0, 4)}`;
}

function Kpi({ label, value, sub, color }) {
  return (
    <div className="card kpi">
      <div className="kpi__label">{label}</div>
      <div className="kpi__value" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="kpi__sub">{sub}</div>}
    </div>
  );
}
