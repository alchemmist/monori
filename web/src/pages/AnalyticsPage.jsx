import { useMemo, useState } from "react";
import { BarChart, LineChart } from "@mantine/charts";
import InlineSelect from "../ui/InlineSelect.jsx";
import { ChartBoundary } from "../components/ChartCard.jsx";
import { useStore } from "../store.js";
import { rub, money, fmtDate, MONTHS_SHORT } from "../format.js";
import {
    monthlySeries,
    yearTotals,
    weekdayProfile,
    dayOfMonthProfile,
    topMerchants,
    txStats,
    disciplineMatrix,
} from "../engine/analytics.js";
import { PALETTE, SERIES, cartesian } from "./chartTheme.js";
import "./dashboard.css";
import "./analytics.css";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Annual report: planning discipline, year-over-year shape, spending patterns. */
export default function AnalyticsPage({ results, firstYear, lastYear }) {
    const { snapshot } = useStore();
    const now = useMemo(() => new Date(), []);
    const [year, setYear] = useState(String(now.getFullYear()));

    const years = [];
    for (let y = firstYear; y <= Math.min(lastYear, now.getFullYear()); y++) years.push(String(y));

    const monthly = useMemo(() => monthlySeries(snapshot), [snapshot]);
    const perYear = useMemo(() => yearTotals(monthly), [monthly]);
    const thisYear = perYear.find((r) => r.year === year);

    const discipline = useMemo(() => {
        const res = results.get(+year);
        const upToMonth = +year === now.getFullYear() ? now.getMonth() : 11;
        return disciplineMatrix(res, snapshot.categories, snapshot.groups, { upToMonth });
    }, [results, snapshot.categories, snapshot.groups, year, now]);

    // Plan vs fact: budgeted total per month vs actual expenses. Spent bars flip to
    // expense-red when they overshoot that month's budget (looked up by value).
    const planFact = useMemo(() => {
        const res = results.get(+year);
        const overColor = new Map();
        const data = MONTHS_SHORT.map((mo, m) => {
            const v = monthly.find(([k]) => k === `${year}-${String(m + 1).padStart(2, "0")}`);
            const spent = Math.round((v ? v[1].expense : 0) / 100);
            const budgeted = Math.round(res.budgetedTotal[m] / 100);
            overColor.set(spent, spent > budgeted ? SERIES.expense : SERIES.accent);
            return { month: mo, Budgeted: budgeted, Spent: spent };
        });
        return { data, overColor };
    }, [results, monthly, year]);

    // Year over year: monthly expenses, selected year vs two previous (older recede)
    const yoy = useMemo(() => {
        const yrs = [+year - 2, +year - 1, +year].filter((y) => y >= firstYear);
        const dims = [SERIES.hint, SERIES.secondary, SERIES.accent];
        const data = MONTHS_SHORT.map((mo, m) => {
            const row = { month: mo };
            for (const y of yrs) {
                const v = monthly.find(([k]) => k === `${y}-${String(m + 1).padStart(2, "0")}`);
                row[String(y)] = v ? Math.round(v[1].expense / 100) : null;
            }
            return row;
        });
        const series = yrs.map((y, i) => ({
            name: String(y),
            color: dims[i + (3 - yrs.length)],
        }));
        return { data, series, current: String(+year) };
    }, [monthly, year, firstYear]);

    const weekdayData = useMemo(() => {
        const sums = weekdayProfile(snapshot, year);
        const total = sums.reduce((s, v) => s + v, 0) || 1;
        return sums.map((v, i) => ({
            day: WEEKDAYS[i],
            Share: Math.round((v / total) * 100),
            color: i >= 5 ? SERIES.accent : PALETTE[0],
        }));
    }, [snapshot, year]);

    const domData = useMemo(() => {
        const sums = dayOfMonthProfile(snapshot, year);
        return sums.map((v, i) => ({ day: String(i + 1), Spent: Math.round(v / 100) }));
    }, [snapshot, year]);

    const merchants = useMemo(() => topMerchants(snapshot, year, 10), [snapshot, year]);
    const merchantsData = useMemo(
        () => merchants.map((m) => ({ name: m.name, Spent: Math.round(m.total / 100) })),
        [merchants],
    );

    const stats = useMemo(() => txStats(snapshot, year), [snapshot, year]);

    return (
        <div className="fade-in dash-section">
            <h2 className="section-title">
                Yearly analytics
                <InlineSelect value={year} onChange={setYear} data={years} />
            </h2>

            <div className="kpi-row">
                <Kpi label="Income" value={`${rub(thisYear?.income ?? 0)} ₽`} sub={year} />
                <Kpi label="Expenses" value={`${rub(thisYear?.expense ?? 0)} ₽`} sub={year} />
                <Kpi
                    label="Net saved"
                    value={`${rub(thisYear?.net ?? 0)} ₽`}
                    color={(thisYear?.net ?? 0) >= 0 ? "var(--m-income)" : "var(--m-expense)"}
                    sub={year}
                />
                <Kpi
                    label="Savings rate"
                    value={
                        thisYear?.savingsRate != null ? `${thisYear.savingsRate.toFixed(0)}%` : "—"
                    }
                    color={
                        (thisYear?.savingsRate ?? 0) >= 0 ? "var(--m-income)" : "var(--m-expense)"
                    }
                    sub={year}
                />
                <Kpi
                    label="Budget hit rate"
                    value={discipline.hitRate != null ? `${discipline.hitRate.toFixed(0)}%` : "—"}
                    color={
                        discipline.hitRate >= 80
                            ? "var(--m-income)"
                            : discipline.hitRate >= 60
                              ? "var(--m-warning)"
                              : "var(--m-expense)"
                    }
                    sub="category-months within budget"
                />
                <Kpi
                    label="Over budget"
                    value={`${rub(discipline.totalOverrun)} ₽`}
                    color={discipline.totalOverrun > 0 ? "var(--m-expense)" : "var(--m-text-faint)"}
                    sub={
                        discipline.worst
                            ? `worst: ${discipline.worst.category.name}`
                            : "no overruns"
                    }
                />
            </div>

            <div className="charts-grid">
                <div className="card chart-card chart-card_wide">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Plan vs fact · {year}</div>
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <BarChart
                                h="100%"
                                data={planFact.data}
                                dataKey="month"
                                series={[
                                    { name: "Budgeted", color: SERIES.hint },
                                    { name: "Spent", color: SERIES.accent },
                                ]}
                                withLegend
                                getBarColor={(value, series) =>
                                    series.name === "Budgeted"
                                        ? SERIES.hint
                                        : (planFact.overColor.get(value) ?? SERIES.accent)
                                }
                                {...cartesian}
                            />
                        </ChartBoundary>
                    </div>
                </div>

                <div className="card chart-card chart-card_wide">
                    <div className="chart-card__head">
                        <div className="chart-card__title">
                            Budget discipline · {year}
                            <span className="chart-card__hint">
                                {" "}
                                · spent vs budgeted, per envelope
                            </span>
                        </div>
                        <div className="disc-legend">
                            <span>
                                <i className="disc-swatch disc-swatch_ok" /> ≤ 100%
                            </span>
                            <span>
                                <i className="disc-swatch disc-swatch_warn" /> 100–120%
                            </span>
                            <span>
                                <i className="disc-swatch disc-swatch_over" /> &gt; 120%
                            </span>
                            <span>
                                <i className="disc-swatch disc-swatch_nobudget" /> unbudgeted spend
                            </span>
                        </div>
                    </div>
                    <DisciplineGrid rows={discipline.rows} year={year} />
                </div>

                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Expenses year over year</div>
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <LineChart
                                h="100%"
                                data={yoy.data}
                                dataKey="month"
                                series={yoy.series}
                                withDots={false}
                                connectNulls={false}
                                lineProps={(s) => ({
                                    strokeWidth: s.name === yoy.current ? 2 : 1.5,
                                })}
                                {...cartesian}
                            />
                        </ChartBoundary>
                    </div>
                </div>

                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Yearly report · all time</div>
                    </div>
                    <div className="chart-card__body chart-card__body_auto">
                        <table className="report-table">
                            <thead>
                                <tr>
                                    <th>Year</th>
                                    <th>Income</th>
                                    <th>Expenses</th>
                                    <th>Net</th>
                                    <th>Rate</th>
                                    <th>Avg/mo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {perYear.map((r) => (
                                    <tr
                                        key={r.year}
                                        className={
                                            r.year === year ? "report-table__row_current" : ""
                                        }
                                    >
                                        <td>{r.year}</td>
                                        <td className="num">{rub(r.income)}</td>
                                        <td className="num">{rub(r.expense)}</td>
                                        <td
                                            className="num"
                                            style={{
                                                color:
                                                    r.net >= 0
                                                        ? "var(--m-income)"
                                                        : "var(--m-expense)",
                                            }}
                                        >
                                            {rub(r.net)}
                                        </td>
                                        <td className="num">
                                            {r.savingsRate != null
                                                ? `${r.savingsRate.toFixed(0)}%`
                                                : "—"}
                                        </td>
                                        <td className="num">{rub(r.avgExpense)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Spending by weekday · {year}</div>
                        <span className="chart-card__hint">% of year total</span>
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <BarChart
                                h="100%"
                                data={weekdayData}
                                dataKey="day"
                                series={[{ name: "Share", color: PALETTE[0] }]}
                                unit="%"
                                {...cartesian}
                            />
                        </ChartBoundary>
                    </div>
                </div>

                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Spending by day of month · {year}</div>
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <BarChart
                                h="100%"
                                data={domData}
                                dataKey="day"
                                series={[{ name: "Spent", color: PALETTE[0] }]}
                                gridAxis="x"
                                {...cartesian}
                            />
                        </ChartBoundary>
                    </div>
                </div>

                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Top merchants · {year}</div>
                    </div>
                    <div className="chart-card__body">
                        {merchants.length ? (
                            <ChartBoundary>
                                <BarChart
                                    h="100%"
                                    orientation="vertical"
                                    data={merchantsData}
                                    dataKey="name"
                                    series={[{ name: "Spent", color: SERIES.accent }]}
                                    yAxisProps={{ width: 110 }}
                                    {...cartesian}
                                />
                            </ChartBoundary>
                        ) : (
                            <div className="chart-card__empty">
                                No categorized expenses in {year}
                            </div>
                        )}
                    </div>
                </div>

                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Transaction stats · {year}</div>
                    </div>
                    <div className="chart-card__body chart-card__body_auto">
                        <div className="stat-list">
                            <div className="stat-list__row">
                                <span>Expense transactions</span>
                                <span className="num">{stats.count}</span>
                            </div>
                            <div className="stat-list__row">
                                <span>Median expense</span>
                                <span className="num">{money(stats.median)}</span>
                            </div>
                            <div className="stat-list__row">
                                <span>Per month</span>
                                <span className="num">{(stats.count / 12).toFixed(0)}</span>
                            </div>
                            {stats.largest && (
                                <div className="stat-list__row stat-list__row_tall">
                                    <span>
                                        Largest expense
                                        <div className="stat-list__hint">
                                            {stats.largest.description.slice(0, 48)} ·{" "}
                                            {fmtDate(stats.largest.date)}
                                        </div>
                                    </span>
                                    <span className="num" style={{ color: "var(--m-expense)" }}>
                                        {money(stats.largest.amount)}
                                    </span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function DisciplineGrid({ rows, year }) {
    if (!rows.length) {
        return <div className="chart-card__empty">No budgeted envelopes in {year}</div>;
    }
    return (
        <div className="disc-wrap">
            <table className="disc-grid">
                <thead>
                    <tr>
                        <th />
                        {MONTHS_SHORT.map((m) => (
                            <th key={m}>{m}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map(({ category, cells }) => (
                        <tr key={category.id}>
                            <td className="disc-grid__name">{category.name}</td>
                            {cells.map((cell, m) => (
                                <td key={m}>
                                    <div
                                        className={`disc-cell ${discClass(cell)}`}
                                        title={discTitle(category, cell, m)}
                                    />
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function discClass(cell) {
    if (cell.ratio == null) return "";
    if (cell.ratio === Infinity) return "disc-cell_nobudget";
    if (cell.ratio <= 1) return "disc-cell_ok";
    if (cell.ratio <= 1.2) return "disc-cell_warn";
    return "disc-cell_over";
}

function discTitle(category, cell, m) {
    if (cell.ratio == null) return `${category.name} · ${MONTHS_SHORT[m]}: —`;
    const pct = cell.ratio === Infinity ? "no budget" : `${Math.round(cell.ratio * 100)}%`;
    return `${category.name} · ${MONTHS_SHORT[m]}: ${rub(cell.spent)} / ${rub(cell.budgeted)} ₽ (${pct})`;
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
