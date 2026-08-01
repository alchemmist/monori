import { useCallback, useEffect, useState, type MouseEvent } from "react";
import { AreaChart, BarChart } from "@mantine/charts";
import { Button } from "@mantine/core";
import { ChartBoundary } from "../components/ChartCard.jsx";
import { api } from "../api.js";
import { money, normalizeKop } from "../format.js";
import { SERIES, cartesian } from "./chartTheme.js";
import { showToast } from "../ui/notify.js";
import { useStore } from "../store.js";
import "./dashboard.css";
import "./admin.css";
import type {
    AdminActivity,
    AdminConnectionSummary,
    AdminOverview,
    AdminUserDetail,
    AdminUserSummary,
    Id,
} from "../types.js";

const fmtDt = (s: string | null | undefined) =>
    s == null || s === "" ? "—" : s.slice(0, 16).replace("T", " ");
const fmtDate = (s: string | null | undefined) => (s == null || s === "" ? "—" : s.slice(0, 10));

const fmtBytes = (n: number | null | undefined) => {
    if (n == null) return "—";
    let v = n;
    for (const unit of ["B", "KB", "MB", "GB"]) {
        if (v < 1024 || unit === "GB") return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${unit}`;
        v /= 1024;
    }
    return `${v.toFixed(1)} GB`;
};

export default function AdminPage() {
    const [overview, setOverview] = useState<AdminOverview | null>(null);
    const [users, setUsers] = useState<AdminUserSummary[] | null>(null);
    const [activity, setActivity] = useState<AdminActivity | null>(null);
    const [detail, setDetail] = useState<AdminUserDetail | null>(null);
    const [error, setError] = useState<string | null>(null);

    const reload = useCallback(() => {
        Promise.all([api.adminOverview(), api.adminUsers(), api.adminActivity()])
            .then(([o, u, a]) => {
                setOverview(o);
                setUsers(u);
                setActivity(a);
            })
            .catch((e) => setError(String(e)));
    }, []);

    useEffect(() => {
        reload();
    }, [reload]);

    // persistent tabs signal admin-data mutations through the store instead of
    // holding a callback into this (possibly unmounted) page
    const openTab = useStore((s) => s.openTab);
    const adminTick = useStore((s) => s.adminTick);
    useEffect(() => {
        if (adminTick === 0) return;
        reload();
        setDetail((d) => {
            if (d != null) {
                api.adminUserDetail(d.user.id)
                    .then(setDetail)
                    .catch(() => setDetail(null));
            }
            return d;
        });
    }, [adminTick, reload]);

    const openDetail = (id: Id) => {
        if (detail?.user.id === id) {
            setDetail(null);
            return;
        }
        api.adminUserDetail(id)
            .then(setDetail)
            .catch((e) =>
                showToast({ title: "Failed to load user", content: String(e), theme: "danger" }),
            );
    };

    if (error != null && error !== "")
        return <div className="admin-error">Failed to load admin data: {error}</div>;
    if (overview == null || users == null || activity == null) return null;

    return (
        <div className="fade-in">
            <div className="admin-page__head">
                <h1 className="page-title">Admin</h1>
                <Button
                    size="xs"
                    variant="subtle"
                    onClick={() => openTab("admin-sql", {}, "admin-sql")}
                >
                    SQL console
                </Button>
            </div>

            <div className="kpi-row admin-kpis">
                <Kpi
                    label="Users"
                    value={overview.totals.users}
                    sub={`+${overview.newUsers30d} in 30 days`}
                />
                <Kpi
                    label="Active users"
                    value={overview.activeUsers7d}
                    color="var(--m-income)"
                    sub="last 7 days"
                />
                <Kpi label="New users" value={overview.newUsers7d} sub="last 7 days" />
                <Kpi
                    label="Transactions"
                    value={overview.totals.transactions.toLocaleString("ru-RU")}
                    sub="all users"
                />
                <Kpi label="Accounts" value={overview.totals.accounts} sub="all users" />
                <Kpi label="Bank connections" value={overview.totals.connections} sub="all users" />
                <Kpi label="Database" value={fmtBytes(overview.dbSizeBytes)} sub="on disk" />
            </div>

            <div className="charts-grid">
                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Registrations by month</div>
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <BarChart
                                h="100%"
                                data={overview.registrations}
                                dataKey="month"
                                series={[
                                    { name: "count", label: "Registrations", color: SERIES.accent },
                                ]}
                                {...cartesian}
                            />
                        </ChartBoundary>
                    </div>
                </div>
                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">
                            API activity
                            <span className="chart-card__hint"> · requests per day, 30 days</span>
                        </div>
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <AreaChart
                                h="100%"
                                data={activity.daily}
                                dataKey="day"
                                series={[
                                    { name: "count", label: "Requests", color: SERIES.income },
                                ]}
                                withDots={false}
                                xAxisProps={{
                                    tickFormatter: (d: string) => d.slice(5),
                                    minTickGap: 24,
                                }}
                                {...cartesian}
                            />
                        </ChartBoundary>
                    </div>
                </div>
                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">
                            Feature usage
                            <span className="chart-card__hint"> · last 30 days</span>
                        </div>
                    </div>
                    <div className="chart-card__body">
                        <ChartBoundary>
                            <BarChart
                                h="100%"
                                data={activity.features}
                                dataKey="feature"
                                series={[
                                    { name: "count", label: "Requests", color: SERIES.warning },
                                ]}
                                {...cartesian}
                            />
                        </ChartBoundary>
                    </div>
                </div>
                <div className="card chart-card">
                    <div className="chart-card__head">
                        <div className="chart-card__title">Recent logins</div>
                    </div>
                    <ul className="admin-logins">
                        {activity.recentLogins.slice(0, 12).map((l, i) => (
                            <li key={i}>
                                <span>{l.email}</span>
                                <span className="num">{fmtDt(l.at)}</span>
                            </li>
                        ))}
                        {activity.recentLogins.length === 0 && (
                            <li className="admin-empty">No logins yet</li>
                        )}
                    </ul>
                </div>
            </div>

            <div className="card admin-users">
                <div className="chart-card__head">
                    <div className="chart-card__title">Users</div>
                </div>
                <table className="admin-table">
                    <thead>
                        <tr>
                            <th>Email</th>
                            <th>Registered</th>
                            <th>Last login</th>
                            <th className="num">Accounts</th>
                            <th className="num">Transactions</th>
                            <th>Last transaction</th>
                            <th className="num">Budgets</th>
                            <th>Bank sync</th>
                            <th />
                        </tr>
                    </thead>
                    <tbody>
                        {users.map((u) => (
                            <UserRow
                                key={u.id}
                                user={u}
                                open={detail?.user.id === u.id}
                                onOpen={() => openDetail(u.id)}
                                onDeleted={() => {
                                    setDetail(null);
                                    reload();
                                }}
                            />
                        ))}
                    </tbody>
                </table>
                {detail && <UserDetail detail={detail} />}
            </div>
        </div>
    );
}

function Kpi({
    label,
    value,
    sub,
    color,
}: {
    label: string;
    value: string | number;
    sub: string;
    color?: string;
}) {
    return (
        <div className="card kpi">
            <div className="kpi__label">{label}</div>
            <div
                className="kpi__value"
                style={color == null || color === "" ? undefined : { color }}
            >
                {value}
            </div>
            {sub !== "" && <div className="kpi__sub">{sub}</div>}
        </div>
    );
}

function SyncBadge({ connection }: { connection?: AdminConnectionSummary | null }) {
    if (connection == null) return <span className="admin-muted">—</span>;
    const tone =
        connection.status === "connected"
            ? "var(--m-income)"
            : connection.status === "error"
              ? "var(--m-expense)"
              : "var(--m-warning)";
    return (
        <span className="admin-sync" title={connection.lastError ?? undefined}>
            <span className="admin-sync__dot" style={{ background: tone }} />
            {connection.status}
            {connection.lastSync != null && connection.lastSync !== "" && (
                <span className="admin-muted"> · {fmtDate(connection.lastSync)}</span>
            )}
        </span>
    );
}

function UserRow({
    user,
    open,
    onOpen,
    onDeleted,
}: {
    user: AdminUserSummary;
    open: boolean;
    onOpen: () => void;
    onDeleted: () => void;
}) {
    const [arming, setArming] = useState(false);
    const [busy, setBusy] = useState(false);

    const remove = async (e: MouseEvent<HTMLButtonElement>) => {
        e.stopPropagation();
        if (!arming) {
            setArming(true);
            return;
        }
        setBusy(true);
        try {
            await api.adminDeleteUser(user.id);
            useStore.getState().closeTabByKey(`admin-tx:${user.id}`);
            showToast({ title: "User deleted", content: user.email, theme: "success" });
            onDeleted();
        } catch (err) {
            showToast({ title: "Delete failed", content: String(err), theme: "danger" });
            setBusy(false);
            setArming(false);
        }
    };

    return (
        <tr
            className={open ? "admin-row_open" : undefined}
            onClick={onOpen}
            onMouseLeave={() => setArming(false)}
        >
            <td>
                {user.email}
                {user.isAdmin === true && <span className="admin-badge">admin</span>}
            </td>
            <td className="num">{fmtDate(user.createdAt)}</td>
            <td className="num">{fmtDt(user.lastLogin)}</td>
            <td className="num">{user.accounts}</td>
            <td className="num">{user.transactions.toLocaleString("ru-RU")}</td>
            <td className="num">{fmtDate(user.lastTransaction)}</td>
            <td className="num">{user.budgets}</td>
            <td>
                <SyncBadge
                    {...(user.connection === undefined ? {} : { connection: user.connection })}
                />
            </td>
            <td className="admin-actions">
                {user.isAdmin !== true && (
                    <Button
                        size="xs"
                        variant="subtle"
                        color="red"
                        loading={busy}
                        onClick={(event) => void remove(event)}
                    >
                        {arming ? "Sure?" : "Delete"}
                    </Button>
                )}
            </td>
        </tr>
    );
}

const TX_PREVIEW = 5;

function UserDetail({ detail }: { detail: AdminUserDetail }) {
    const openTab = useStore((s) => s.openTab);
    const openFull = async () => {
        // open the tab inside the click gesture so it is not popup-blocked, then
        // point it at a plain-text blob of one JSON transaction per line
        const w = window.open("", "_blank", "noopener");
        try {
            // the endpoint is paged (capped server-side); walk offset until a
            // short page signals the end so a heavy history still loads in full
            const PAGE = 1000;
            const rows = [];
            for (let offset = 0; ; offset += PAGE) {
                const page = await api.adminUserTransactions(detail.user.id, {
                    limit: PAGE,
                    offset,
                });
                rows.push(...page);
                if (page.length < PAGE) break;
            }
            const text = rows.map((r) => JSON.stringify(r)).join("\n");
            const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
            if (w) w.location = url;
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch (e) {
            if (w) w.close();
            showToast({
                title: "Failed to load transactions",
                content: String(e),
                theme: "danger",
            });
        }
    };

    return (
        <div className="admin-detail">
            <div className="admin-detail__col">
                <div className="admin-detail__title">Accounts</div>
                <ul className="admin-logins">
                    {detail.accounts.map((a) => (
                        <li key={a.id}>
                            <span>
                                {a.name}
                                <span className="admin-muted"> · {a.transactions} tx</span>
                            </span>
                            <span className="num">{money(a.balance)}</span>
                        </li>
                    ))}
                    {detail.accounts.length === 0 && <li className="admin-empty">No accounts</li>}
                </ul>
                <div className="admin-detail__title">Feature usage</div>
                <ul className="admin-logins">
                    {detail.featureUsage.map((f) => (
                        <li key={f.feature}>
                            <span>{f.feature}</span>
                            <span className="num">{f.count.toLocaleString("ru-RU")}</span>
                        </li>
                    ))}
                    {detail.featureUsage.length === 0 && (
                        <li className="admin-empty">No API activity</li>
                    )}
                </ul>
                <div className="admin-detail__title">Recent logins</div>
                <ul className="admin-logins">
                    {detail.recentLogins.slice(0, 8).map((at, i) => (
                        <li key={i}>
                            <span className="num">{fmtDt(at)}</span>
                        </li>
                    ))}
                    {detail.recentLogins.length === 0 && (
                        <li className="admin-empty">Never logged in</li>
                    )}
                </ul>
            </div>
            <div className="admin-detail__col admin-detail__col_wide">
                <div className="admin-detail__title admin-detail__head">
                    <span>Recent transactions</span>
                    <span className="admin-detail__actions">
                        {detail.recentTransactions.length > 0 && (
                            <Button size="xs" variant="subtle" onClick={() => void openFull()}>
                                Full
                            </Button>
                        )}
                        <Button
                            size="xs"
                            variant="subtle"
                            onClick={() =>
                                openTab(
                                    "admin-tx",
                                    { user: detail.user },
                                    `admin-tx:${detail.user.id}`,
                                )
                            }
                        >
                            Manage
                        </Button>
                    </span>
                </div>
                <table className="admin-table admin-table_compact">
                    <tbody>
                        {detail.recentTransactions.slice(0, TX_PREVIEW).map((t) => (
                            <tr key={t.id}>
                                <td className="num">{fmtDate(t.date)}</td>
                                <td>
                                    {t.description !== ""
                                        ? t.description
                                        : t.category !== ""
                                          ? t.category
                                          : "—"}
                                </td>
                                <td className="admin-muted">{t.account}</td>
                                <td
                                    className="num"
                                    style={{
                                        color:
                                            normalizeKop(t.amount) >= 0
                                                ? "var(--m-income)"
                                                : undefined,
                                    }}
                                >
                                    {money(t.amount)}
                                </td>
                            </tr>
                        ))}
                        {detail.recentTransactions.length === 0 && (
                            <tr>
                                <td className="admin-empty">No transactions</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
