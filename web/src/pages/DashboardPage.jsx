import { useMemo, useState } from "react";
import { AreaChart, BarChart, CompositeChart, DonutChart } from "@mantine/charts";
import { ChartBoundary } from "../components/ChartCard.jsx";
import TimeNavigator from "../components/TimeNavigator.jsx";
import { Button } from "@mantine/core";
import InlineSelect from "../ui/InlineSelect.jsx";
import { useStore } from "../store.js";
import { accountBalances } from "../engine/analytics.js";
import AccountBadge from "../components/AccountBadge.jsx";
import { rub, money, MONTHS_SHORT } from "../format.js";
import { PALETTE, SERIES, cartesian } from "./chartTheme.js";
import "./dashboard.css";

const PRESETS = [
    { id: "6m", label: "6m", months: 6 },
    { id: "1y", label: "1y", months: 12 },
    { id: "3y", label: "3y", months: 36 },
    { id: "5y", label: "5y", months: 60 },
    { id: "ytd", label: "YTD" },
    { id: "all", label: "All" },
];

// Income/expense bars + a savings-rate line on a secondary axis.
const TREND_SERIES = [
    { name: "Income", color: SERIES.income, type: "bar" },
    { name: "Expenses", color: SERIES.expense, type: "bar" },
    { name: "Savings rate %", color: SERIES.accent, type: "line", yAxisId: "right" },
];

// 'YYYY-MM' → "Jan '24" for the trend/cumulative x-axis ticks
function fmtMonthTick(key) {
    if (!key) return "";
    return `${MONTHS_SHORT[+key.slice(5, 7) - 1]} '${key.slice(2, 4)}`;
}

/** Analytics count "To be Budgeted" as real inflow (it holds actual money
 * injections). Internal transfers are uncategorized and thus excluded. */
export default function DashboardPage({ firstYear, lastYear }) {
    const { snapshot } = useStore();
    const now = useMemo(() => new Date(), []);
    const [donutYear, setDonutYear] = useState(String(now.getFullYear()));
    const [donutActive, setDonutActive] = useState(null); // legend-hovered category name
    const [drillCat, setDrillCat] = useState(() =>
        String(snapshot.categories.find((c) => c.name === "Groceries")?.id ?? ""),
    );
    const [drillYear, setDrillYear] = useState(String(now.getFullYear()));
    const [stackYear, setStackYear] = useState(String(now.getFullYear()));
    const [catStackYear, setCatStackYear] = useState(String(now.getFullYear()));
    const [acctFilter, setAcctFilter] = useState("all");

    const accounts = snapshot.accounts ?? [];
    const balances = useMemo(() => accountBalances(snapshot), [snapshot]);
    const txns = useMemo(
        () =>
            acctFilter === "all"
                ? snapshot.transactions
                : snapshot.transactions.filter((t) => t.accountId === +acctFilter),
        [snapshot.transactions, acctFilter],
    );

    const excludedIds = useMemo(() => new Set(), []);
    const incomeGroupIds = useMemo(
        () => new Set(snapshot.groups.filter((g) => g.kind === "income").map((g) => g.id)),
        [snapshot.groups],
    );
    const catById = useMemo(
        () => new Map(snapshot.categories.map((c) => [c.id, c])),
        [snapshot.categories],
    );

    // Monthly series over full history: real income / expenses (kopecks, positive numbers)
    const monthly = useMemo(() => {
        const map = new Map(); // 'y-m' -> {income, expense}
        for (const t of txns) {
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
    }, [txns, excludedIds, incomeGroupIds, catById]);

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

    // Chart 1: income/expense bars + savings rate line over the selected window.
    // 1-2-1 weighted moving average on the rate so the line reads as a calm curve.
    const trendData = useMemo(() => {
        const rows = closed.slice(trendLo, trendHi + 1);
        const rate = (j) => {
            const v = rows[Math.max(0, Math.min(rows.length - 1, j))][1];
            return v.income > 0
                ? Math.max(-100, Math.min(100, ((v.income - v.expense) / v.income) * 100))
                : null;
        };
        return rows.map(([k, v], i) => {
            const [a, b, c] = [rate(i - 1), rate(i), rate(i + 1)];
            let sr = null;
            if (b != null) {
                const parts = [
                    [a, 1],
                    [b, 2],
                    [c, 1],
                ].filter(([x]) => x != null);
                const w = parts.reduce((s, [, ww]) => s + ww, 0);
                sr = Math.round(parts.reduce((s, [x, ww]) => s + x * ww, 0) / w);
            }
            return {
                x: k,
                Income: v.income / 100,
                Expenses: v.expense / 100,
                "Savings rate %": sr,
            };
        });
    }, [closed, trendLo, trendHi]);

    // Chart 2: donut by category for a year
    const donutData = useMemo(() => {
        const sums = new Map();
        for (const t of txns) {
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
        return top.map(([name, v], i) => ({
            name,
            value: Math.round(v / 100),
            color: PALETTE[i % PALETTE.length],
        }));
    }, [txns, donutYear, catById, incomeGroupIds, excludedIds]);

    // Chart 3: selected category by month for a year
    const drillName = drillCat ? catById.get(+drillCat)?.name : "";
    const drillData = useMemo(() => {
        const catId = drillCat ? +drillCat : null;
        const sums = Array(12).fill(0);
        if (catId != null) {
            for (const t of txns) {
                if (t.categoryId !== catId || !t.date.startsWith(drillYear)) continue;
                sums[+t.date.slice(5, 7) - 1] += Math.abs(t.amount);
            }
        }
        return sums.map((v, i) => ({ month: MONTHS_SHORT[i], Spent: Math.round(v / 100) }));
    }, [txns, drillCat, drillYear]);

    // Chart 4: cumulative net over all history
    const cumulativeData = useMemo(() => {
        let acc = 0;
        return monthly.map(([k, v]) => {
            acc += v.income - v.expense;
            return { x: k, "Cumulative net": Math.round(acc / 100) };
        });
    }, [monthly]);

    // Chart 5: expense structure by group, stacked, its own year selector
    const groupStack = useMemo(() => {
        const expenseGroups = snapshot.groups.filter((g) => g.kind === "expense");
        const perGroup = new Map(expenseGroups.map((g) => [g.id, Array(12).fill(0)]));
        for (const t of txns) {
            if (!t.date.startsWith(stackYear) || t.categoryId == null || t.amount >= 0) continue;
            const cat = catById.get(t.categoryId);
            if (!cat || !perGroup.has(cat.groupId) || excludedIds.has(t.categoryId)) continue;
            perGroup.get(cat.groupId)[+t.date.slice(5, 7) - 1] -= t.amount;
        }
        const data = MONTHS_SHORT.map((mo, m) => {
            const row = { month: mo };
            for (const g of expenseGroups) row[`g${g.id}`] = Math.round(perGroup.get(g.id)[m] / 100);
            return row;
        });
        const series = expenseGroups.map((g, i) => ({
            name: `g${g.id}`,
            label: g.name,
            color: PALETTE[i % PALETTE.length],
        }));
        return { data, series };
    }, [txns, snapshot.groups, stackYear, catById, excludedIds]);

    // Spending by category, stacked by month — same top-N categories (and thus
    // colors) as the donut, so the two views line up.
    const catStack = useMemo(() => {
        const perCat = new Map(); // name -> Array(12) monthly outflow totals
        for (const t of txns) {
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
        const names = top.map((r) => r.name);
        const other = Array(12).fill(0);
        if (rest.length) {
            for (const r of rest) r.arr.forEach((v, m) => (other[m] += v));
            names.push("Other");
        }
        const data = MONTHS_SHORT.map((mo, m) => {
            const row = { month: mo };
            top.forEach((r) => (row[r.name] = Math.round(r.arr[m] / 100)));
            if (rest.length) row.Other = Math.round(other[m] / 100);
            return row;
        });
        const series = names.map((name, i) => ({ name, color: PALETTE[i % PALETTE.length] }));
        return { data, series };
    }, [txns, catStackYear, catById, incomeGroupIds, excludedIds]);

    const years = [];
    for (let y = firstYear; y <= Math.min(lastYear, now.getFullYear()); y++) years.push(String(y));

    const expenseCatOptions = snapshot.categories
        .filter((c) => !incomeGroupIds.has(c.groupId))
        .map((c) => ({ value: String(c.id), label: c.name }));

    return (
        <div className="fade-in">
            <div className="dash-head">
                <h1 className="page-title" style={{ margin: 0 }}>
                    Dashboard
                </h1>
                {accounts.length > 1 && (
                    <InlineSelect
                        value={acctFilter}
                        onChange={setAcctFilter}
                        data={[
                            { value: "all", label: "All accounts" },
                            ...accounts.map((a) => ({ value: String(a.id), label: a.name })),
                        ]}
                    />
                )}
            </div>

            {accounts.length > 0 && (
                <div className="balance-row">
                    {accounts.map((a) => {
                        return (
                            <div key={a.id} className="card balance-card">
                                <div className="balance-card__name">
                                    <AccountBadge account={a} size={20} /> {a.name}
                                </div>
                                <div
                                    className="balance-card__value num"
                                    style={{
                                        color:
                                            (balances.get(a.id) ?? 0) < 0
                                                ? "var(--m-expense)"
                                                : undefined,
                                    }}
                                >
                                    {money(balances.get(a.id) ?? 0)}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            <div className="kpi-row">
                <Kpi
                    label="Net year to date"
                    value={`${rub(kpis.netYtd)} ₽`}
                    color={kpis.netYtd >= 0 ? "var(--m-income)" : "var(--m-expense)"}
                    sub={`${now.getFullYear()}`}
                />
                <Kpi
                    label="Savings rate"
                    value={`${kpis.savingsRate.toFixed(0)}%`}
                    color={kpis.savingsRate >= 0 ? "var(--m-income)" : "var(--m-expense)"}
                    sub="last 12 months"
                />
                <Kpi
                    label="Avg monthly spend"
                    value={`${rub(kpis.exp12avg)} ₽`}
                    sub="last 12 months"
                />
                <Kpi
                    label="Spent this month"
                    value={`${rub(kpis.cur.expense)} ₽`}
                    sub={`vs ${rub(kpis.prev.expense)} ₽ last month`}
                />
                <Kpi
                    label="Daily rate"
                    value={`${rub(kpis.dailyRate)} ₽`}
                    sub="this month, per day"
                />
                <Kpi
                    label="Month forecast"
                    value={`${rub(kpis.forecast)} ₽`}
                    color={kpis.forecast > kpis.exp12avg ? "var(--m-warning)" : "var(--m-income)"}
                    sub="at current pace"
                />
                <Kpi
                    label="Saved"
                    value={`${rub(kpis.saved12)} ₽`}
                    color={kpis.saved12 >= 0 ? "var(--m-income)" : "var(--m-expense)"}
                    sub="last 12 months"
                />
                <Kpi
                    label="Runway"
                    value={kpis.runway != null ? `${kpis.runway.toFixed(1)} mo` : "—"}
                    color={kpis.runway != null && kpis.runway < 3 ? "var(--m-warning)" : undefined}
                    sub="all-time net ÷ avg monthly spend"
                />
            </div>

            <div className="charts-grid">
                <div className="card chart-card chart-card_wide">
                    <div className="chart-card__head">
                        <div className="chart-card__title">
                            Income vs expenses · {fmtMonthKey(closed[trendLo]?.[0])} —{" "}
                            {fmtMonthKey(closed[trendHi]?.[0])}
                            <span className="chart-card__hint">
                                {" "}
                                · {trendHi - trendLo + 1} months · drag to zoom
                            </span>
                        </div>
                        <div className="preset-row">
                            {PRESETS.map((p) => (
                                <Button
                                    key={p.id}
                                    size="s"
                                    variant="subtle"
                                    data-tone={activePreset === p.id ? undefined : "secondary"}
                                    data-selected={activePreset === p.id || undefined}
                                    onClick={() => setTrendRange(presetRange(p.id))}
                                >
                                    {p.label}
                                </Button>
                            ))}
                        </div>
                    </div>
                    <div className="chart-card__body chart-card__body_tall">
                        <ChartBoundary>
                            <CompositeChart
                                h="100%"
                                data={trendData}
                                dataKey="x"
                                series={TREND_SERIES}
                                withLegend
                                withDots={false}
                                connectNulls={false}
                                withRightYAxis
                                rightYAxisProps={{ tickFormatter: (v) => `${v}%` }}
                                xAxisProps={{ tickFormatter: fmtMonthTick, minTickGap: 24 }}
                                {...cartesian}
                            />
                        </ChartBoundary>
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
                        <InlineSelect
                            small
                            value={donutYear}
                            onChange={setDonutYear}
                            data={years}
                        />
                    </div>
                    <div className="chart-card__body chart-donut">
                        <ChartBoundary>
                            <DonutChart
                                data={donutData}
                                size={196}
                                thickness={36}
                                paddingAngle={0}
                                strokeWidth={0}
                                tooltipDataSource="segment"
                                valueFormatter={(v) => `${v.toLocaleString("ru-RU")} ₽`}
                                cellProps={(cell) => ({
                                    opacity: donutActive && cell.name !== donutActive ? 0.3 : 1,
                                    style: { transition: "opacity 120ms" },
                                })}
                            />
                        </ChartBoundary>
                        <ul className="donut-legend">
                            {donutData.map((d) => (
                                <li
                                    key={d.name}
                                    data-dim={
                                        donutActive && d.name !== donutActive ? "" : undefined
                                    }
                                    onMouseEnter={() => setDonutActive(d.name)}
                                    onMouseLeave={() => setDonutActive(null)}
                                >
                                    <span
                                        className="donut-legend__dot"
                                        style={{ background: d.color }}
                                    />
                                    {d.name}
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>

                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Category by month</div>
                        <div style={{ display: "flex", gap: 8 }}>
                            <InlineSelect
                                small
                                searchable
                                placeholder="Category"
                                value={drillCat || null}
                                onChange={(v) => setDrillCat(v ?? "")}
                                data={expenseCatOptions}
                            />
                            <InlineSelect
                                small
                                value={drillYear}
                                onChange={setDrillYear}
                                data={years}
                            />
                        </div>
                    </div>
                    <div className="chart-card__body">
                        {drillCat ? (
                            <ChartBoundary>
                                <BarChart
                                    h="100%"
                                    data={drillData}
                                    dataKey="month"
                                    series={[
                                        { name: "Spent", label: drillName, color: SERIES.accent },
                                    ]}
                                    {...cartesian}
                                />
                            </ChartBoundary>
                        ) : (
                            <div
                                style={{
                                    display: "grid",
                                    placeItems: "center",
                                    height: "100%",
                                    color: "var(--m-text-faint)",
                                }}
                            >
                                Pick a category to see its monthly spending
                            </div>
                        )}
                    </div>
                </div>

                <div className="card chart-card chart-card_wide">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Spending by category · by month</div>
                        <InlineSelect
                            small
                            value={catStackYear}
                            onChange={setCatStackYear}
                            data={years}
                        />
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <BarChart
                                h="100%"
                                type="stacked"
                                data={catStack.data}
                                dataKey="month"
                                series={catStack.series}
                                withLegend
                                {...cartesian}
                            />
                        </ChartBoundary>
                    </div>
                </div>

                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Cumulative net · all time</div>
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <AreaChart
                                h="100%"
                                data={cumulativeData}
                                dataKey="x"
                                series={[{ name: "Cumulative net", color: SERIES.income }]}
                                withDots={false}
                                fillOpacity={0.25}
                                strokeWidth={2}
                                xAxisProps={{ tickFormatter: fmtMonthTick, minTickGap: 24 }}
                                {...cartesian}
                            />
                        </ChartBoundary>
                    </div>
                </div>

                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Expense structure by group</div>
                        <InlineSelect
                            small
                            value={stackYear}
                            onChange={setStackYear}
                            data={years}
                        />
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <BarChart
                                h="100%"
                                type="stacked"
                                data={groupStack.data}
                                dataKey="month"
                                series={groupStack.series}
                                withLegend
                                {...cartesian}
                            />
                        </ChartBoundary>
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
            <div className="kpi__value" style={color ? { color } : undefined}>
                {value}
            </div>
            {sub && <div className="kpi__sub">{sub}</div>}
        </div>
    );
}
