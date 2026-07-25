import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ActionIcon, Button, CloseButton } from "@mantine/core";
import { FTextInput } from "../ui/fields.jsx";
import InlineSelect from "../ui/InlineSelect.jsx";
import Tag from "../ui/Tag.jsx";
import ProgressRing from "../ui/ProgressRing.jsx";
import {
    ArrowDownToLine,
    ArrowRightArrowLeft,
    ArrowUpToLine,
    Eye,
    EyeSlash,
    Magnifier,
} from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { orderedGroups, categoriesByGroup } from "../categoryOrder.js";
import { money, fmtDate } from "../format.js";
import { useWindowedRows } from "../useWindowedRows.js";
import { compareTx } from "../mergeTransactions.js";
import ImportDialog from "../components/ImportDialog.jsx";
import TransferDialog from "../components/TransferDialog.jsx";
import TransferRow from "../components/TransferRow.jsx";
import TransferSuggestions from "../components/TransferSuggestions.jsx";
import { mergeTransferRows } from "../engine/transfers.js";
import "./budget.css";
import "./transfers.css";

// td is a fixed 38px + a 1px bottom border; measured for real on mount so zoom
// or font metrics can't let the windowing math drift over thousands of rows
const ROW_H_FALLBACK = 39;

export default function TransactionsPage() {
    const {
        snapshot,
        txProgress,
        setTxCategory,
        setTxAccount,
        hiddenTx,
        loadHiddenTx,
        hideTx,
        unhideTx,
        splitTransfer,
        deleteTransferWithLegs,
        notify,
    } = useStore();
    const [query, setQuery] = useState("");
    const [catFilter, setCatFilter] = useState("all");
    const [yearFilter, setYearFilter] = useState("all");
    const [acctFilter, setAcctFilter] = useState("all");
    const [showHidden, setShowHidden] = useState(false);

    // hidden rows are not in the snapshot at all; the first toggle fetches them
    useEffect(() => {
        if (showHidden) loadHiddenTx();
    }, [showHidden, loadHiddenTx]);
    const [importing, setImporting] = useState(false);
    const [transferring, setTransferring] = useState(false);
    const [suggesting, setSuggesting] = useState(false);
    const [expanded, setExpanded] = useState(() => new Set());
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

    // categories in the exact order arranged on the kanban board — groups first
    // (group.sort), then categories within each group (category.sort). `catOptions`
    // is the flat ordered list for the top filter; `catSections` are labelled,
    // group-tinted sections for the per-row picker. Archived ones are dropped here
    // and only re-surfaced by `catSectionsFor` when a row still points at one.
    const { catOptions, catSections } = useMemo(() => {
        const groups = orderedGroups(snapshot.groups);
        const byGroup = categoriesByGroup(snapshot.categories, groups);
        const flat = [];
        const sections = [];
        for (const g of groups) {
            const opts = (byGroup.get(g.id) ?? [])
                .filter((c) => !c.archived)
                .map((c) => ({ value: String(c.id), label: c.name }));
            flat.push(...opts);
            if (opts.length)
                sections.push({ id: g.id, group: g.name, kind: g.kind, options: opts });
        }
        return { catOptions: flat, catSections: sections };
    }, [snapshot.groups, snapshot.categories]);

    const catById = useMemo(
        () => new Map(snapshot.categories.map((c) => [c.id, c])),
        [snapshot.categories],
    );
    const groupById = useMemo(
        () => new Map(snapshot.groups.map((g) => [g.id, g])),
        [snapshot.groups],
    );

    // like acctOptionsFor: an archived category is missing from the sections, so
    // when this row still points at one, surface it under its own group so the
    // value renders and can be kept or changed.
    const catSectionsFor = (t) => {
        const cur = t.categoryId != null ? catById.get(t.categoryId) : null;
        if (!cur || !cur.archived) return catSections;
        const g = groupById.get(cur.groupId);
        const opt = { value: String(cur.id), label: cur.name };
        const clone = catSections.map((s) => ({ ...s, options: [...s.options] }));
        const sec = clone.find((s) => s.id === cur.groupId);
        if (sec) sec.options.push(opt);
        else
            clone.push({
                id: cur.groupId,
                group: g?.name ?? "Archived",
                kind: g?.kind,
                options: [opt],
            });
        return clone;
    };

    // merged (and sorted) once here, so typing in the search box only refilters
    // instead of re-sorting the whole ledger on every keystroke
    const combined = useMemo(() => {
        if (!showHidden || !hiddenTx?.length) return snapshot.transactions;
        return [...snapshot.transactions, ...hiddenTx].sort(compareTx);
    }, [snapshot.transactions, hiddenTx, showHidden]);

    const years = useMemo(() => {
        const s = new Set(combined.map((t) => t.date.slice(0, 4)));
        return [...s].sort().reverse();
    }, [combined]);

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        let rows = combined;
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
    }, [combined, query, catFilter, yearFilter, acctFilter]);

    // the two legs of a transfer are one row here; every item is still exactly
    // one row tall, so the windowing math below stays on a fixed row height
    const items = useMemo(
        () => mergeTransferRows(filtered, snapshot.transactions, expanded),
        [filtered, snapshot.transactions, expanded],
    );

    const toggleTransfer = (transferId) =>
        setExpanded((prev) => {
            const next = new Set(prev);
            if (!next.delete(transferId)) next.add(transferId);
            return next;
        });

    const runTransferAction = (action, title) => async (transferId) => {
        try {
            await action(transferId);
            notify({ title, theme: "success" });
        } catch (e) {
            notify({ title: "Failed to update the transfer", theme: "danger", content: String(e) });
        }
    };

    // an ordinary ledger row. `leg` marks one half of an expanded transfer: the
    // same row, indented and muted, so it reads as belonging to the row above
    const renderTxRow = (t, leg) => (
        <tr
            key={leg ? `l${t.id}` : t.id}
            className={`cat-row${leg ? " tx-row_leg" : ""}${t.hidden ? " tx-hidden-row" : ""}`}
        >
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
                {t.transferId != null && !leg && (
                    <Tag theme="info" style={{ marginLeft: 8 }}>
                        transfer
                    </Tag>
                )}
                {t.hidden && <Tag style={{ marginLeft: 8 }}>hidden</Tag>}
                {t.transferId == null && !leg && (
                    <ActionIcon
                        className="tx-row-action"
                        size={24}
                        variant="subtle"
                        aria-label={t.hidden ? "Unhide transaction" : "Hide transaction"}
                        title={t.hidden ? "Unhide transaction" : "Hide transaction"}
                        onClick={() => (t.hidden ? unhideTx(t.id) : hideTx(t.id))}
                    >
                        {t.hidden ? (
                            <Eye width={14} height={14} />
                        ) : (
                            <EyeSlash width={14} height={14} />
                        )}
                    </ActionIcon>
                )}
            </td>
            <td style={{ textAlign: "left", color: "var(--m-text-dim)" }}>{t.bankCategory}</td>
            <td>
                <span className={`money num ${t.amount > 0 ? "money_pos" : ""}`}>
                    {money(t.amount)}
                </span>
            </td>
            <td style={{ textAlign: "left" }}>
                {t.transferId != null || t.hidden ? (
                    <span style={{ color: "var(--m-text-dim)", paddingLeft: 4 }}>
                        {acctName.get(t.accountId) ?? "—"}
                    </span>
                ) : (
                    <InlineSelect
                        small
                        borderless
                        value={t.accountId != null ? String(t.accountId) : null}
                        onChange={(v) => v && setTxAccount(t.id, +v)}
                        data={acctOptionsFor(t)}
                    />
                )}
            </td>
            <td style={{ textAlign: "left" }}>
                {t.transferId != null || t.hidden ? (
                    <span style={{ color: "var(--m-text-faint)", paddingLeft: 4 }}>
                        {t.hidden ? (catById.get(t.categoryId)?.name ?? "—") : "—"}
                    </span>
                ) : (
                    <InlineSelect
                        small
                        borderless
                        searchable
                        placeholder="—"
                        value={t.categoryId != null ? String(t.categoryId) : null}
                        onChange={(v) => setTxCategory(t.id, v ? +v : null)}
                        data={catSectionsFor(t)}
                    />
                )}
            </td>
        </tr>
    );

    // measure a real row once it's on screen so the spacer math matches the DOM
    useLayoutEffect(() => {
        const row = bodyRef.current?.querySelector("tr.cat-row");
        const h = row?.getBoundingClientRect().height;
        if (h && Math.abs(h - rowH) > 0.5) setRowH(h);
    }, [items.length, rowH]);

    const { start, end, padTop, padBottom } = useWindowedRows({
        count: items.length,
        rowHeight: rowH,
        anchorRef: bodyRef,
    });
    const visibleRows = items.slice(start, end);

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
                <Button
                    variant={showHidden ? "light" : "default"}
                    size="m"
                    aria-pressed={showHidden}
                    onClick={() => setShowHidden((v) => !v)}
                    leftSection={
                        showHidden ? (
                            <Eye width={14} height={14} />
                        ) : (
                            <EyeSlash width={14} height={14} />
                        )
                    }
                >
                    Hidden
                </Button>
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
                    variant="default"
                    size="m"
                    onClick={() => setSuggesting(true)}
                    disabled={activeAccounts.length < 2}
                >
                    Find transfers
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

            <div
                style={{
                    marginBottom: 10,
                    color: "var(--m-text-dim)",
                    fontSize: 12,
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                }}
            >
                <span>{filtered.length} transactions</span>
                {showHidden && hiddenTx && <span>{hiddenTx.length} hidden shown</span>}
                {txProgress && (
                    <ProgressRing
                        value={txProgress.total ? txProgress.loaded / txProgress.total : 0}
                        label={`Loading older transactions: ${txProgress.loaded} of ${txProgress.total}`}
                    />
                )}
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
                        {visibleRows.map((item) =>
                            item.kind === "transfer" ? (
                                <TransferRow
                                    key={item.key}
                                    item={item}
                                    accountName={(id) => acctName.get(id) ?? "—"}
                                    expanded={expanded.has(item.transferId)}
                                    onToggle={() => toggleTransfer(item.transferId)}
                                    onSplit={() =>
                                        runTransferAction(
                                            splitTransfer,
                                            "Transfer split",
                                        )(item.transferId)
                                    }
                                    onDelete={() =>
                                        runTransferAction(
                                            deleteTransferWithLegs,
                                            "Transfer deleted",
                                        )(item.transferId)
                                    }
                                />
                            ) : (
                                renderTxRow(item.tx, item.kind === "leg")
                            ),
                        )}
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
            {suggesting && <TransferSuggestions onClose={() => setSuggesting(false)} />}
        </div>
    );
}
