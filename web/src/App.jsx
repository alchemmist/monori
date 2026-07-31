import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { Loader } from "@mantine/core";
import {
    ChartColumn,
    ListUl,
    Tags,
    LayoutHeaderCellsLarge,
    ChevronLeft,
    ChevronRight,
    Gear,
    Wallet,
    ChartLine,
    Receipt,
    ChartPie,
    ClockArrowRotateLeft,
    SlidersVertical,
    Book,
    Bug,
    PersonGear,
} from "@gravity-ui/icons";
import { useStore, isDemo } from "./store.js";
import { api } from "./api.js";
import { showToast } from "./ui/notify.js";
import { computeRange, firstBudgetYear } from "./engine/budget.js";
import BudgetPage from "./pages/BudgetPage.jsx";

// the whole d3/charts stack is only used here — keep it out of the entry chunk
const DashboardPage = lazy(() => import("./pages/DashboardPage.jsx"));
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage.jsx"));
const AdminPage = lazy(() => import("./pages/AdminPage.jsx"));
import TransactionsPage from "./pages/TransactionsPage.jsx";
import AccountsPage from "./pages/AccountsPage.jsx";
import CategoriesPage from "./pages/CategoriesPage.jsx";
import RecurringPage from "./pages/RecurringPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import TabHost from "./components/TabHost.jsx";

const NAV = [
    { id: "budget", title: "Budget", icon: LayoutHeaderCellsLarge },
    { id: "dashboard", title: "Dashboard", icon: ChartColumn },
    { id: "transactions", title: "Transactions", icon: ListUl },
    { id: "recurring", title: "Recurring", icon: ClockArrowRotateLeft },
    { id: "accounts", title: "Accounts", icon: Wallet },
    { id: "categories", title: "Categories", icon: Tags },
];

// planned destinations from the roadmap — shown disabled until their issue ships
const SOON = [
    { title: "Net worth", icon: ChartLine, issue: 19 },
    { title: "Debts & loans", icon: Receipt, issue: 20 },
    { title: "Reports", icon: ChartPie, issue: 18 },
    { title: "Import history", icon: ClockArrowRotateLeft, issue: 22 },
    { title: "Rules", icon: SlidersVertical, issue: 21 },
];

// the sidebar's bug button opens a pre-labelled GitHub issue carrying the
// skeleton a usable report needs, so the reporter is not staring at an empty box
const REPORT_BUG_URL = `https://github.com/alchemmist/monori/issues/new?labels=bug&body=${encodeURIComponent(
    "**What happened**\n\n\n**What I expected**\n\n\n**Steps to reproduce**\n\n1. \n",
)}`;

// where the budget chain starts for an account with nothing in it yet; with data,
// firstBudgetYear reads the real one off the snapshot

const DEFAULT_FIRST_YEAR = 2020;

export default function App({ theme, onToggleTheme }) {
    const {
        snapshot,
        loading,
        txProgress,
        error,
        load,
        toast,
        user,
        authChecked,
        checkAuth,
        openTab,
    } = useStore();
    const [page, setPage] = useState("budget");
    const [collapsed, setCollapsed] = useState(
        () => localStorage.getItem("sidebar_collapsed") === "1",
    );
    const toggleSidebar = () =>
        setCollapsed((c) => {
            const next = !c;
            localStorage.setItem("sidebar_collapsed", next ? "1" : "0");
            return next;
        });

    useEffect(() => {
        checkAuth();
    }, [checkAuth]);

    useEffect(() => {
        if (isDemo()) {
            load();
        } else if (user) {
            // Materialize schedules before loading the ledger so recurring
            // transactions appear on every page, not only after visiting Recurring.
            Promise.resolve()
                .then(() => api.recurring())
                .catch(() => null)
                .then(() => load());
        }
    }, [load, user]);

    useEffect(() => {
        if (toast) showToast(toast);
    }, [toast]);

    useEffect(() => {
        if (!isDemo() && user && window.location.pathname === "/login") {
            window.history.replaceState(null, "", "/");
        }
    }, [user]);

    const firstYear = useMemo(() => firstBudgetYear(snapshot, DEFAULT_FIRST_YEAR), [snapshot]);

    const lastYear = useMemo(() => {
        if (!snapshot) return new Date().getFullYear();
        const maxTx = snapshot.transactions.reduce(
            (m, t) => Math.max(m, +t.date.slice(0, 4)),
            DEFAULT_FIRST_YEAR,
        );
        const maxBudget = snapshot.budgets.reduce(
            (m, b) => Math.max(m, b.year),
            DEFAULT_FIRST_YEAR,
        );
        return Math.max(maxTx, maxBudget, new Date().getFullYear()) + 1;
    }, [snapshot]);

    // A light snapshot is followed by progressively older transaction pages.
    // Computing and painting the budget for every intermediate snapshot makes
    // its balances visibly jump year by year. Keep derived pages behind a
    // loadscreen and calculate them once, from the completed ledger.
    const results = useMemo(
        () => (snapshot && !txProgress ? computeRange(snapshot, firstYear, lastYear) : null),
        [snapshot, txProgress, firstYear, lastYear],
    );

    if (!isDemo() && !authChecked) {
        return (
            <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
                <Loader size="lg" type="bars" />
            </div>
        );
    }
    if (!isDemo() && !user) {
        if (window.location.pathname === "/login") {
            return <LoginPage />;
        }
        window.location.replace("/welcome");
        return null;
    }
    if (loading) {
        return (
            <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
                <Loader size="lg" type="bars" />
            </div>
        );
    }
    if (error) {
        return (
            <div
                style={{
                    display: "grid",
                    placeItems: "center",
                    height: "100vh",
                    color: "var(--m-expense)",
                }}
            >
                Failed to load data: {error}
            </div>
        );
    }

    return (
        <div className="layout">
            <nav className={`sidebar ${collapsed ? "sidebar_collapsed" : ""}`}>
                <div className="sidebar__head">
                    <div className="sidebar__logo" title="monori">
                        <span className="sidebar__logo-mark">も</span>
                        <span className="sidebar__logo-tail">
                            の<span>り</span>
                        </span>
                    </div>
                </div>
                {NAV.map(({ id, title, icon: Icon }) => (
                    <button
                        key={id}
                        className={`sidebar__item ${page === id ? "sidebar__item_active" : ""}`}
                        onClick={() => setPage(id)}
                        title={collapsed ? title : undefined}
                    >
                        <Icon width={16} height={16} />
                        <span className="sidebar__label">{title}</span>
                    </button>
                ))}

                <div className="sidebar__gap" />
                {SOON.map(({ title, icon: Icon }) => (
                    <div
                        key={title}
                        className="sidebar__item sidebar__item_soon"
                        aria-disabled="true"
                        title={collapsed ? `${title} — in development` : "In development"}
                    >
                        <Icon width={16} height={16} />
                        <span className="sidebar__label">{title}</span>
                    </div>
                ))}

                <div className="sidebar__bottom">
                    {user?.isAdmin && (
                        <button
                            className={`sidebar__item ${page === "admin" ? "sidebar__item_active" : ""}`}
                            onClick={() => setPage("admin")}
                            title={collapsed ? "Admin" : undefined}
                        >
                            <PersonGear width={16} height={16} />
                            <span className="sidebar__label">Admin</span>
                        </button>
                    )}
                    <a
                        className="sidebar__item"
                        href="/docs"
                        target="_blank"
                        rel="noreferrer"
                        title={collapsed ? "Docs" : undefined}
                    >
                        <Book width={16} height={16} />
                        <span className="sidebar__label">Docs</span>
                    </a>
                    <a
                        className="sidebar__item"
                        href={REPORT_BUG_URL}
                        target="_blank"
                        rel="noreferrer"
                        title="Report a bug on GitHub"
                    >
                        <Bug width={16} height={16} />
                        <span className="sidebar__label">Report a bug</span>
                    </a>
                    <button
                        className={`sidebar__item ${page === "settings" ? "sidebar__item_active" : ""}`}
                        onClick={() => setPage("settings")}
                        title={collapsed ? "Settings" : user?.email}
                    >
                        <Gear width={16} height={16} />
                        <span className="sidebar__label">Settings</span>
                    </button>
                    <button
                        className="sidebar__collapse"
                        onClick={toggleSidebar}
                        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                    >
                        {collapsed ? (
                            <ChevronRight width={16} height={16} />
                        ) : (
                            <ChevronLeft width={16} height={16} />
                        )}
                    </button>
                </div>
            </nav>
            <main className="content">
                {isDemo() && (
                    <div className="demo-banner">
                        <span className="demo-banner__badge">Demo</span>
                        <span>Sample data — changes aren’t saved.</span>
                        <a
                            className="demo-banner__link"
                            href="https://github.com/alchemmist/monori"
                            target="_blank"
                            rel="noreferrer"
                        >
                            View on GitHub →
                        </a>
                    </div>
                )}
                {page === "budget" &&
                    (txProgress ? (
                        <DerivedDataLoadscreen progress={txProgress} />
                    ) : (
                        <BudgetPage results={results} firstYear={firstYear} lastYear={lastYear} />
                    ))}
                {page === "dashboard" && txProgress && (
                    <DerivedDataLoadscreen progress={txProgress} />
                )}
                {page === "dashboard" && !txProgress && (
                    <Suspense
                        fallback={
                            <div style={{ display: "grid", placeItems: "center", height: "60vh" }}>
                                <Loader size="lg" type="bars" />
                            </div>
                        }
                    >
                        <DashboardPage firstYear={firstYear} lastYear={lastYear} />
                        <AnalyticsPage
                            results={results}
                            firstYear={firstYear}
                            lastYear={lastYear}
                        />
                    </Suspense>
                )}
                {page === "transactions" && <TransactionsPage />}
                {page === "recurring" && <RecurringPage />}
                {page === "accounts" && <AccountsPage />}
                {page === "categories" && <CategoriesPage />}
                {page === "admin" && user?.isAdmin && (
                    <Suspense
                        fallback={
                            <div style={{ display: "grid", placeItems: "center", height: "60vh" }}>
                                <Loader size="lg" type="bars" />
                            </div>
                        }
                    >
                        <AdminPage />
                    </Suspense>
                )}
                {page === "settings" && (
                    <SettingsPage
                        theme={theme}
                        onToggleTheme={onToggleTheme}
                        onMigrate={() => openTab("migrate", {}, "migrate")}
                    />
                )}
            </main>
            <TabHost />
        </div>
    );
}

function DerivedDataLoadscreen({ progress }) {
    const percent = progress.total ? Math.round((progress.loaded / progress.total) * 100) : 0;
    return (
        <div className="derived-loadscreen">
            <Loader size="lg" type="bars" />
            <div className="derived-loadscreen__title">Calculating your budget…</div>
            <div
                className="derived-loadscreen__progress"
                role="progressbar"
                aria-label="Loading transactions"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent}
            >
                Loading transactions · {percent}%
            </div>
        </div>
    );
}
