import { useCallback, useEffect, useState } from "react";
import { AreaChart, BarChart } from "@mantine/charts";
import { Button } from "@mantine/core";
import { ChartBoundary } from "../components/ChartCard.jsx";
import { FTextInput } from "../ui/fields.jsx";
import { api } from "../api.js";
import { money } from "../format.js";
import { SERIES, cartesian } from "./chartTheme.js";
import { showToast } from "../ui/notify.js";
import "./dashboard.css";
import "./admin.css";

const fmtDt = (s) => (s ? s.slice(0, 16).replace("T", " ") : "—");
const fmtDate = (s) => (s ? s.slice(0, 10) : "—");

export default function AdminPage() {
    const [overview, setOverview] = useState(null);
    const [users, setUsers] = useState(null);
    const [activity, setActivity] = useState(null);
    const [detail, setDetail] = useState(null);
    const [error, setError] = useState(null);

    const reload = useCallback(() => {
        Promise.all([api.adminOverview(), api.adminUsers(), api.adminActivity()])
            .then(([o, u, a]) => {
                setOverview(o);
                setUsers(u);
                setActivity(a);
            })
            .catch((e) => setError(e.message));
    }, []);

    useEffect(() => {
        reload();
    }, [reload]);

    const openDetail = (id) => {
        if (detail?.user.id === id) {
            setDetail(null);
            return;
        }
        api.adminUserDetail(id)
            .then(setDetail)
            .catch((e) =>
                showToast({ title: "Failed to load user", content: e.message, theme: "danger" }),
            );
    };

    if (error) return <div className="admin-error">Failed to load admin data: {error}</div>;
    if (!overview || !users || !activity) return null;

    return (
        <div className="fade-in">
            <h1 className="page-title">Admin</h1>

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
                                xAxisProps={{ tickFormatter: (d) => d.slice(5), minTickGap: 24 }}
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

            <CreateUser onCreated={reload} />
        </div>
    );
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

function SyncBadge({ connection }) {
    if (!connection) return <span className="admin-muted">—</span>;
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
            {connection.lastSync && (
                <span className="admin-muted"> · {fmtDate(connection.lastSync)}</span>
            )}
        </span>
    );
}

function UserRow({ user, open, onOpen, onDeleted }) {
    const [arming, setArming] = useState(false);
    const [busy, setBusy] = useState(false);

    const remove = async (e) => {
        e.stopPropagation();
        if (!arming) {
            setArming(true);
            return;
        }
        setBusy(true);
        try {
            await api.adminDeleteUser(user.id);
            showToast({ title: "User deleted", content: user.email, theme: "success" });
            onDeleted();
        } catch (err) {
            showToast({ title: "Delete failed", content: err.message, theme: "danger" });
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
                {user.isAdmin && <span className="admin-badge">admin</span>}
            </td>
            <td className="num">{fmtDate(user.createdAt)}</td>
            <td className="num">{fmtDt(user.lastLogin)}</td>
            <td className="num">{user.accounts}</td>
            <td className="num">{user.transactions.toLocaleString("ru-RU")}</td>
            <td className="num">{fmtDate(user.lastTransaction)}</td>
            <td className="num">{user.budgets}</td>
            <td>
                <SyncBadge connection={user.connection} />
            </td>
            <td className="admin-actions">
                {!user.isAdmin && (
                    <Button size="xs" variant="subtle" color="red" loading={busy} onClick={remove}>
                        {arming ? "Sure?" : "Delete"}
                    </Button>
                )}
            </td>
        </tr>
    );
}

function UserDetail({ detail }) {
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
                <div className="admin-detail__title">Recent transactions</div>
                <table className="admin-table admin-table_compact">
                    <tbody>
                        {detail.recentTransactions.map((t) => (
                            <tr key={t.id}>
                                <td className="num">{fmtDate(t.date)}</td>
                                <td>{t.description || t.category || "—"}</td>
                                <td className="admin-muted">{t.account}</td>
                                <td
                                    className="num"
                                    style={{ color: t.amount >= 0 ? "var(--m-income)" : undefined }}
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

function CreateUser({ onCreated }) {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const u = await api.adminCreateUser(email.trim(), password);
            showToast({ title: "User created", content: u.email, theme: "success" });
            setEmail("");
            setPassword("");
            onCreated();
        } catch (err) {
            showToast({ title: "Create failed", content: err.message, theme: "danger" });
        } finally {
            setBusy(false);
        }
    };

    return (
        <form className="card admin-create" onSubmit={submit}>
            <div className="chart-card__title">Create user</div>
            <FTextInput
                label="Email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
            />
            <FTextInput
                label="Password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="at least 8 characters"
            />
            <Button type="submit" loading={busy} disabled={!email || password.length < 8}>
                Create
            </Button>
        </form>
    );
}
