import { useEffect, useMemo, useState } from "react";
import { Loader, useToaster } from "@gravity-ui/uikit";
import {
  ChartColumn,
  ListUl,
  LayoutHeaderCellsLarge,
  ChevronLeft,
  ChevronRight,
  Gear,
  Wallet,
  ChartLine,
  Target,
  Receipt,
  ChartPie,
  ClockArrowRotateLeft,
  SlidersVertical,
} from "@gravity-ui/icons";
import { useStore, isDemo } from "./store.js";
import { computeRange } from "./engine/budget.js";
import BudgetPage from "./pages/BudgetPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import AnalyticsPage from "./pages/AnalyticsPage.jsx";
import TransactionsPage from "./pages/TransactionsPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

const NAV = [
  { id: "budget", title: "Budget", icon: LayoutHeaderCellsLarge },
  { id: "dashboard", title: "Dashboard", icon: ChartColumn },
  { id: "transactions", title: "Transactions", icon: ListUl },
];

// planned destinations from the roadmap — shown disabled until their issue ships
const SOON = [
  { title: "Accounts", icon: Wallet, issue: 2 },
  { title: "Net worth", icon: ChartLine, issue: 19 },
  { title: "Goals", icon: Target, issue: 15 },
  { title: "Debts & loans", icon: Receipt, issue: 20 },
  { title: "Reports", icon: ChartPie, issue: 18 },
  { title: "Import history", icon: ClockArrowRotateLeft, issue: 22 },
  { title: "Rules", icon: SlidersVertical, issue: 21 },
];

const FIRST_YEAR = 2020;

export default function App({ theme, onToggleTheme }) {
  const { snapshot, loading, error, load, toast } = useStore();
  const [page, setPage] = useState("budget");
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar_collapsed") === "1");
  const toaster = useToaster();

  const toggleSidebar = () =>
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem("sidebar_collapsed", next ? "1" : "0");
      return next;
    });

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (toast) toaster.add({ name: String(Date.now()), autoHiding: 5000, ...toast });
  }, [toast, toaster]);

  const lastYear = useMemo(() => {
    if (!snapshot) return new Date().getFullYear();
    const maxTx = snapshot.transactions.reduce((m, t) => Math.max(m, +t.date.slice(0, 4)), FIRST_YEAR);
    const maxBudget = snapshot.budgets.reduce((m, b) => Math.max(m, b.year), FIRST_YEAR);
    return Math.max(maxTx, maxBudget, new Date().getFullYear()) + 1;
  }, [snapshot]);

  const results = useMemo(
    () => (snapshot ? computeRange(snapshot, FIRST_YEAR, lastYear) : null),
    [snapshot, lastYear]
  );

  if (loading) {
    return (
      <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
        <Loader size="l" />
      </div>
    );
  }
  if (error) {
    return (
      <div style={{ display: "grid", placeItems: "center", height: "100vh", color: "var(--m-expense)" }}>
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
            <span className="sidebar__logo-tail">の<span>り</span></span>
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
          <button
            className={`sidebar__item ${page === "settings" ? "sidebar__item_active" : ""}`}
            onClick={() => setPage("settings")}
            title={collapsed ? "Settings" : undefined}
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
            {collapsed ? <ChevronRight width={16} height={16} /> : <ChevronLeft width={16} height={16} />}
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
        {page === "budget" && <BudgetPage results={results} firstYear={FIRST_YEAR} lastYear={lastYear} />}
        {page === "dashboard" && (
          <>
            <DashboardPage results={results} firstYear={FIRST_YEAR} lastYear={lastYear} />
            <AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={lastYear} />
          </>
        )}
        {page === "transactions" && <TransactionsPage />}
        {page === "settings" && <SettingsPage theme={theme} onToggleTheme={onToggleTheme} />}
      </main>
    </div>
  );
}
