import { useEffect, useMemo, useState } from "react";
import { Loader, useToaster } from "@gravity-ui/uikit";
import { ChartColumn, ListUl, LayoutHeaderCellsLarge } from "@gravity-ui/icons";
import { useStore } from "./store.js";
import { computeRange } from "./engine/budget.js";
import BudgetPage from "./pages/BudgetPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import TransactionsPage from "./pages/TransactionsPage.jsx";

const NAV = [
  { id: "budget", title: "Budget", icon: LayoutHeaderCellsLarge },
  { id: "dashboard", title: "Dashboard", icon: ChartColumn },
  { id: "transactions", title: "Transactions", icon: ListUl },
];

const FIRST_YEAR = 2020;

export default function App() {
  const { snapshot, loading, error, load, toast } = useStore();
  const [page, setPage] = useState("budget");
  const toaster = useToaster();

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
      <nav className="sidebar">
        <div className="sidebar__logo">
          mono<span>ri</span>
        </div>
        {NAV.map(({ id, title, icon: Icon }) => (
          <button
            key={id}
            className={`sidebar__item ${page === id ? "sidebar__item_active" : ""}`}
            onClick={() => setPage(id)}
          >
            <Icon width={16} height={16} />
            {title}
          </button>
        ))}
        <div className="sidebar__footer">monori · personal budget</div>
      </nav>
      <main className="content">
        {page === "budget" && <BudgetPage results={results} firstYear={FIRST_YEAR} lastYear={lastYear} />}
        {page === "dashboard" && <DashboardPage results={results} firstYear={FIRST_YEAR} lastYear={lastYear} />}
        {page === "transactions" && <TransactionsPage />}
      </main>
    </div>
  );
}
