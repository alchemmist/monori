import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Button, CloseButton } from "@mantine/core";
import { FTextInput } from "../ui/fields.jsx";
import InlineSelect from "../ui/InlineSelect.jsx";
import Tag from "../ui/Tag.jsx";
import { ArrowDownToLine, ArrowRightArrowLeft, ArrowUpToLine, Magnifier } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { money, fmtDate } from "../format.js";
import { useWindowedRows } from "../useWindowedRows.js";
import ImportDialog from "../components/ImportDialog.jsx";
import TransferDialog from "../components/TransferDialog.jsx";
import "./budget.css";

// td is a fixed 38px + a 1px bottom border; measured for real on mount so zoom
// or font metrics can't let the windowing math drift over thousands of rows
const ROW_H_FALLBACK = 39;

export default function TransactionsPage() {
    const { snapshot, setTxCategory, setTxAccount } = useStore();
    const [query, setQuery] = useState("");
    const [catFilter, setCatFilter] = useState("all");
    const [yearFilter, setYearFilter] = useState("all");
    const [acctFilter, setAcctFilter] = useState("all");
    const [importing, setImporting] = useState(false);
    const [transferring, setTransferring] = useState(false);
    const bodyRef = useRef(null);
    const [rowH, setRowH] = useState(ROW_H_FALLBACK);
    const [showTop, setShowTop] = useState(false);

    // the ledger is one long scroll, so once you're a screenful down offer a jump
    // back to the top (rAF-coalesced so the scroll handler stays cheap)
    useEffect(() => {
        let raf = 0;
        const onScroll = () => {
            if (raf) return;
            raf = requestAnimationFrame(() => {
                raf = 0;
                setShowTop(window.scrollY > window.innerHeight);
            });
        };
        onScroll();
        window.addEventListener("scroll", onScroll, { passive: true });
        return () => {
            window.removeEventListener("scroll", onScroll);
            if (raf) cancelAnimationFrame(raf);
        };
    }, []);

    const accounts = useMemo(() => snapshot.accounts ?? [], [snapshot.accounts]);
    const activeAccounts = useMemo(() => accounts.filter((a) => !a.archived), [accounts]);
    const acctById = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);
    const acctName = useMemo(() => new Map(accounts.map((a) => [a.id, a.name])), [accounts]);
    const acctOptions = useMemo(
        () => activeAccounts.map((a) => ({ value: String(a.id), label: a.name })),
        [activeAccounts],
    );

    // Options for moving a row: active accounts plus this row's own account when it
    // is archived, so the current value still renders and you can leave it there.
    const acctOptionsFor = (t) => {
        const cur = acctById.get(t.accountId);
        if (cur && cur.archived) {
            return [{ value: String(cur.id), label: cur.name }, ...acctOptions];
        }
        return acctOptions;
    };

    const catOptions = useMemo(
        () => snapshot.categories.map((c) => ({ value: String(c.id), label: c.name })),
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
                (t) =>
                    t.description.toLowerCase().includes(q) ||
                    t.bankCategory.toLowerCase().includes(q),
            );
        return [...rows].reverse(); // newest first
    }, [snapshot.transactions, query, catFilter, yearFilter, acctFilter]);

    // measure a real row once it's on screen so the spacer math matches the DOM
    useLayoutEffect(() => {
        const row = bodyRef.current?.querySelector("tr.cat-row");
        const h = row?.getBoundingClientRect().height;
        if (h && Math.abs(h - rowH) > 0.5) setRowH(h);
    }, [filtered.length, rowH]);

    const { start, end, padTop, padBottom } = useWindowedRows({
        count: filtered.length,
        rowHeight: rowH,
        anchorRef: bodyRef,
    });
    const visibleRows = filtered.slice(start, end);

    // a new filter/search jumps back to the top so you're never left staring at
    // a blank gap where you'd scrolled past the (now shorter) list
    const resetScroll = (fn) => (v) => {
        window.scrollTo({ top: 0 });
        fn(v);
    };

    return (
        <div className="fade-in">
            <div className="budget-toolbar">
                <h1 className="page-title" style={{ margin: 0 }}>
                    Transactions
                </h1>
                <FTextInput
                    value={query}
                    onChange={(e) => resetScroll(setQuery)(e.target.value)}
                    placeholder="Search description"
                    label={<Magnifier style={{ marginInline: 6 }} width={14} height={14} />}
                    aria-label="Search description"
                    rightSectionPointerEvents="all"
                    rightSection={
                        query ? (
                            <CloseButton
                                size="sm"
                                aria-label="Clear search"
                                onClick={() => resetScroll(setQuery)("")}
                            />
                        ) : null
                    }
                    style={{ width: 260 }}
                />
                <InlineSelect
                    value={catFilter}
                    onChange={resetScroll(setCatFilter)}
                    data={[
                        { value: "all", label: "All categories" },
                        { value: "none", label: "Uncategorized" },
                        ...catOptions,
                    ]}
                    searchable
                />
                <InlineSelect
                    value={yearFilter}
                    onChange={resetScroll(setYearFilter)}
                    data={[{ value: "all", label: "All years" }, ...years]}
                />
                {activeAccounts.length > 1 && (
                    <InlineSelect
                        value={acctFilter}
                        onChange={resetScroll(setAcctFilter)}
                        data={[{ value: "all", label: "All accounts" }, ...acctOptions]}
                    />
                )}
                <div style={{ flex: 1 }} />
                <Button
                    variant="default"
                    size="m"
                    onClick={() => setTransferring(true)}
                    disabled={activeAccounts.length < 2}
                    leftSection={<ArrowRightArrowLeft width={14} height={14} />}
                >
                    Transfer
                </Button>
                <Button
                    variant="filled"
                    size="m"
                    onClick={() => setImporting(true)}
                    leftSection={<ArrowDownToLine width={14} height={14} />}
                >
                    Import statement
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
                    <tbody ref={bodyRef}>
                        {padTop > 0 && (
                            <tr aria-hidden="true">
                                <td colSpan={6} style={{ height: padTop, padding: 0, border: 0 }} />
                            </tr>
                        )}
                        {visibleRows.map((t) => (
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
                                        <Tag theme="warning" style={{ marginLeft: 8 }}>
                                            adjustment
                                        </Tag>
                                    )}
                                    {t.transferId != null && (
                                        <Tag theme="info" style={{ marginLeft: 8 }}>
                                            transfer
                                        </Tag>
                                    )}
                                </td>
                                <td style={{ textAlign: "left", color: "var(--m-text-dim)" }}>
                                    {t.bankCategory}
                                </td>
                                <td>
                                    <span
                                        className={`money num ${t.amount > 0 ? "money_pos" : ""}`}
                                    >
                                        {money(t.amount)}
                                    </span>
                                </td>
                                <td style={{ textAlign: "left" }}>
                                    {t.transferId != null ? (
                                        <span
                                            style={{ color: "var(--m-text-dim)", paddingLeft: 4 }}
                                        >
                                            {acctName.get(t.accountId) ?? "—"}
                                        </span>
                                    ) : (
                                        <InlineSelect
                                            small
                                            clear
                                            value={t.accountId != null ? String(t.accountId) : null}
                                            onChange={(v) => v && setTxAccount(t.id, +v)}
                                            data={acctOptionsFor(t)}
                                        />
                                    )}
                                </td>
                                <td style={{ textAlign: "left" }}>
                                    {t.transferId != null ? (
                                        <span
                                            style={{ color: "var(--m-text-faint)", paddingLeft: 4 }}
                                        >
                                            —
                                        </span>
                                    ) : (
                                        <InlineSelect
                                            small
                                            clear
                                            searchable
                                            placeholder="—"
                                            value={
                                                t.categoryId != null ? String(t.categoryId) : null
                                            }
                                            onChange={(v) => setTxCategory(t.id, v ? +v : null)}
                                            data={catOptions}
                                        />
                                    )}
                                </td>
                            </tr>
                        ))}
                        {padBottom > 0 && (
                            <tr aria-hidden="true">
                                <td
                                    colSpan={6}
                                    style={{ height: padBottom, padding: 0, border: 0 }}
                                />
                            </tr>
                        )}
                        {filtered.length === 0 && (
                            <tr>
                                <td
                                    colSpan={6}
                                    style={{
                                        textAlign: "center",
                                        color: "var(--m-text-faint)",
                                        height: 80,
                                    }}
                                >
                                    Nothing found
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {showTop && (
                <button
                    type="button"
                    className="scroll-top"
                    aria-label="Back to top"
                    title="Back to top"
                    onClick={() => {
                        // honour reduced-motion: jump instantly instead of panning
                        const reduce = window.matchMedia?.(
                            "(prefers-reduced-motion: reduce)",
                        ).matches;
                        window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
                    }}
                >
                    <ArrowUpToLine width={18} height={18} />
                </button>
            )}

            {importing && <ImportDialog onClose={() => setImporting(false)} />}
            {transferring && (
                <TransferDialog accounts={accounts} onClose={() => setTransferring(false)} />
            )}
        </div>
    );
}
