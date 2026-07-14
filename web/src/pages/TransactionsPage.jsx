import { useMemo, useState } from "react";
import { Button, Pagination, Select, TextInput, Label } from "@gravity-ui/uikit";
import { ArrowDownToLine, ArrowRightArrowLeft, Magnifier } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { money, fmtDate } from "../format.js";
import ImportDialog from "../components/ImportDialog.jsx";
import TransferDialog from "../components/TransferDialog.jsx";
import "./budget.css";

const PAGE_SIZE = 100;

export default function TransactionsPage() {
  const { snapshot, setTxCategory, setTxAccount } = useStore();
  const [query, setQuery] = useState("");
  const [catFilter, setCatFilter] = useState("all");
  const [yearFilter, setYearFilter] = useState("all");
  const [acctFilter, setAcctFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [importing, setImporting] = useState(false);
  const [transferring, setTransferring] = useState(false);

  const accounts = useMemo(() => snapshot.accounts ?? [], [snapshot.accounts]);
  const activeAccounts = useMemo(() => accounts.filter((a) => !a.archived), [accounts]);
  const acctName = useMemo(() => new Map(accounts.map((a) => [a.id, a.name])), [accounts]);
  const acctOptions = useMemo(
    () => accounts.map((a) => ({ value: String(a.id), content: a.name })),
    [accounts],
  );

  const catOptions = useMemo(
    () => snapshot.categories.map((c) => ({ value: String(c.id), content: c.name })),
    [snapshot.categories],
  );

  const years = useMemo(() => {
    const s = new Set(snapshot.transactions.map((t) => t.date.slice(0, 4)));
    return [...s].sort().reverse();
  }, [snapshot.transactions]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = snapshot.transactions;
    if (yearFilter !== "all") rows = rows.filter((t) => t.date.startsWith(yearFilter));
    if (acctFilter !== "all") rows = rows.filter((t) => t.accountId === +acctFilter);
    if (catFilter === "none") rows = rows.filter((t) => t.categoryId == null);
    else if (catFilter !== "all") rows = rows.filter((t) => t.categoryId === +catFilter);
    if (q)
      rows = rows.filter(
        (t) => t.description.toLowerCase().includes(q) || t.bankCategory.toLowerCase().includes(q),
      );
    return [...rows].reverse(); // newest first
  }, [snapshot.transactions, query, catFilter, yearFilter, acctFilter]);

  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const resetPage = (fn) => (v) => {
    setPage(1);
    fn(v);
  };

  return (
    <div className="fade-in">
      <div className="budget-toolbar">
        <h1 className="page-title" style={{ margin: 0 }}>
          Transactions
        </h1>
        <TextInput
          value={query}
          onUpdate={resetPage(setQuery)}
          placeholder="Search description"
          startContent={<Magnifier style={{ marginInline: 6 }} width={14} height={14} />}
          hasClear
          style={{ width: 260 }}
        />
        <Select
          value={[catFilter]}
          onUpdate={resetPage((v) => setCatFilter(v[0]))}
          options={[
            { value: "all", content: "All categories" },
            { value: "none", content: "Uncategorized" },
            ...catOptions,
          ]}
          filterable
        />
        <Select
          value={[yearFilter]}
          onUpdate={resetPage((v) => setYearFilter(v[0]))}
          options={[
            { value: "all", content: "All years" },
            ...years.map((y) => ({ value: y, content: y })),
          ]}
        />
        {activeAccounts.length > 1 && (
          <Select
            value={[acctFilter]}
            onUpdate={resetPage((v) => setAcctFilter(v[0]))}
            options={[{ value: "all", content: "All accounts" }, ...acctOptions]}
          />
        )}
        <div style={{ flex: 1 }} />
        <Button
          view="outlined"
          size="m"
          onClick={() => setTransferring(true)}
          disabled={activeAccounts.length < 2}
        >
          <ArrowRightArrowLeft width={14} height={14} /> Transfer
        </Button>
        <Button view="action" size="m" onClick={() => setImporting(true)}>
          <ArrowDownToLine width={14} height={14} /> Import statement
        </Button>
      </div>

      <div style={{ marginBottom: 10, color: "var(--m-text-dim)", fontSize: 12 }}>
        {filtered.length} transactions
      </div>

      <div className="card tx-table">
        <table className="budget-grid tx-grid">
          <thead>
            <tr>
              <th style={{ textAlign: "left", width: 90 }}>Date</th>
              <th style={{ textAlign: "left" }}>Description</th>
              <th style={{ textAlign: "left", width: 140 }}>Bank category</th>
              <th style={{ width: 120 }}>Amount</th>
              <th style={{ textAlign: "left", width: 150 }}>Account</th>
              <th style={{ textAlign: "left", width: 190 }}>Category</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((t) => (
              <tr key={t.id} className="cat-row">
                <td style={{ textAlign: "left" }} className="num">
                  {fmtDate(t.date)}
                </td>
                <td
                  style={{
                    textAlign: "left",
                    maxWidth: 380,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {t.description}
                  {t.source === "adjustment" && (
                    <Label size="xs" theme="warning" style={{ marginLeft: 8 }}>
                      adjustment
                    </Label>
                  )}
                  {t.transferId != null && (
                    <Label size="xs" theme="info" style={{ marginLeft: 8 }}>
                      transfer
                    </Label>
                  )}
                </td>
                <td style={{ textAlign: "left", color: "var(--m-text-dim)" }}>{t.bankCategory}</td>
                <td>
                  <span className={`money num ${t.amount > 0 ? "money_pos" : ""}`}>
                    {money(t.amount)}
                  </span>
                </td>
                <td style={{ textAlign: "left" }}>
                  {t.transferId != null ? (
                    <span style={{ color: "var(--m-text-dim)", paddingLeft: 4 }}>
                      {acctName.get(t.accountId) ?? "—"}
                    </span>
                  ) : (
                    <Select
                      size="s"
                      view="clear"
                      value={t.accountId != null ? [String(t.accountId)] : []}
                      onUpdate={(v) => v[0] && setTxAccount(t.id, +v[0])}
                      options={acctOptions}
                    />
                  )}
                </td>
                <td style={{ textAlign: "left" }}>
                  {t.transferId != null ? (
                    <span style={{ color: "var(--m-text-faint)", paddingLeft: 4 }}>—</span>
                  ) : (
                    <Select
                      size="s"
                      view="clear"
                      filterable
                      placeholder="—"
                      value={t.categoryId != null ? [String(t.categoryId)] : []}
                      onUpdate={(v) => setTxCategory(t.id, v[0] ? +v[0] : null)}
                      options={catOptions}
                    />
                  )}
                </td>
              </tr>
            ))}
            {pageRows.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  style={{ textAlign: "center", color: "var(--m-text-faint)", height: 80 }}
                >
                  Nothing found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {filtered.length > PAGE_SIZE && (
        <div style={{ marginTop: 14, display: "flex", justifyContent: "center" }}>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={filtered.length}
            onUpdate={(p) => setPage(p)}
            compact
          />
        </div>
      )}

      {importing && <ImportDialog onClose={() => setImporting(false)} />}
      {transferring && (
        <TransferDialog accounts={accounts} onClose={() => setTransferring(false)} />
      )}
    </div>
  );
}
