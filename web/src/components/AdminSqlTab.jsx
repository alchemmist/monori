import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Textarea } from "@mantine/core";
import { api } from "../api.js";
import { useStore } from "../store.js";
import Tab from "../ui/Tab.jsx";
import Txt from "../ui/Txt.jsx";
import { showToast } from "../ui/notify.js";
import { loadHistory, remember } from "./sqlHistory.js";

const CELL_MAX = 200;

const renderCell = (v) => {
    const s = String(v);
    return s.length > CELL_MAX ? `${s.slice(0, CELL_MAX)}…` : s;
};

const rowsLabel = (n) => `${n} ${n === 1 ? "row" : "rows"}`;

/* SQL console over the live database, docked as a Tab so the admin page stays
 * readable next to the results. Reads run straight through; a write is refused
 * once by the server (rolled back, with the row count it would have touched)
 * and only applies after the admin confirms that count — the refusal doubles as
 * a dry run. */
export default function AdminSqlTab({ onClose }) {
    const [sql, setSql] = useState("");
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [pendingWrite, setPendingWrite] = useState(null);
    const [history, setHistory] = useState(loadHistory);
    const areaRef = useRef(null);

    useEffect(() => {
        areaRef.current?.focus();
    }, []);

    const run = useCallback(
        async (confirmWrite = false, dryRun = false) => {
            const statement = sql.trim();
            if (!statement || busy) return;
            setBusy(true);
            setError(null);
            setPendingWrite(null);
            try {
                const r = await api.adminSql(statement, confirmWrite, dryRun);
                setResult(r);
                setHistory(remember(statement));
                if (r.kind === "write") {
                    showToast({
                        title: `${rowsLabel(r.rowCount)} affected`,
                        content: statement,
                        theme: "success",
                    });
                    useStore.getState().bumpAdminTick();
                }
            } catch (e) {
                setResult(null);
                // the server refuses writes on the first pass and says how many
                // rows they would hit; turn that into the confirmation prompt
                if (!confirmWrite && e.message.includes("needs confirmation")) {
                    setPendingWrite(e.message);
                } else {
                    setError(e.message);
                }
            } finally {
                setBusy(false);
            }
        },
        [sql, busy],
    );

    const onKeyDown = (e) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            run(false, e.shiftKey);
        }
    };

    const footer = (
        <>
            <Txt tone="secondary" caption style={{ marginRight: "auto", alignSelf: "center" }}>
                ⌘/Ctrl + Enter · ⇧ for a dry run
            </Txt>
            {pendingWrite ? (
                <Button size="l" variant="subtle" onClick={() => setPendingWrite(null)}>
                    Cancel
                </Button>
            ) : (
                <Button
                    size="l"
                    variant="subtle"
                    loading={busy}
                    disabled={!sql.trim()}
                    onClick={() => run(false, true)}
                    title="Run inside a transaction and roll it back — nothing is committed"
                >
                    Dry run
                </Button>
            )}
            <Button
                size="l"
                variant="filled"
                color={pendingWrite ? "red" : undefined}
                loading={busy}
                disabled={!sql.trim()}
                onClick={() => run(Boolean(pendingWrite))}
            >
                {pendingWrite ? "Apply write" : "Run"}
            </Button>
        </>
    );

    return (
        <Tab title="SQL console" strip="SQL" onClose={onClose} footer={footer} wide>
            {/* a plain Textarea, not the inline-label FTextArea: SQL is written
                on several lines and wants the whole box */}
            <Textarea
                ref={areaRef}
                aria-label="SQL statement"
                autosize
                minRows={4}
                maxRows={14}
                spellCheck={false}
                value={sql}
                onChange={(e) => {
                    setSql(e.currentTarget.value);
                    setPendingWrite(null);
                }}
                onKeyDown={onKeyDown}
                placeholder="SELECT * FROM transactions ORDER BY date DESC LIMIT 20"
                styles={{
                    input: {
                        fontFamily: "var(--g-font-family-monospace, ui-monospace, monospace)",
                    },
                }}
            />

            {pendingWrite && <div className="sql-console__warn">{pendingWrite}</div>}
            {error && <div className="sql-console__error">{error}</div>}

            {result?.kind === "dry" && (
                <div className="sql-console__dry">
                    Rolled back — nothing was written.{" "}
                    {result.wouldWrite
                        ? `Applying this would affect ${rowsLabel(result.rowCount)}.`
                        : `The query returned ${rowsLabel(result.rowCount)}.`}
                </div>
            )}

            {result && (
                <>
                    <Txt tone="secondary" caption block>
                        {result.kind === "write" || (result.kind === "dry" && result.wouldWrite)
                            ? `${rowsLabel(result.rowCount)} affected`
                            : rowsLabel(result.rowCount)}
                        {` · ${result.elapsedMs} ms`}
                        {result.truncated && ` · showing first ${result.rowCount} rows`}
                    </Txt>
                    {result.columns.length > 0 && (
                        <div className="sql-console__scroll">
                            <table className="admin-table admin-table_compact sql-console__table">
                                <thead>
                                    <tr>
                                        {result.columns.map((col, i) => (
                                            <th key={i}>{col}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {result.rows.map((row, i) => (
                                        <tr key={i}>
                                            {row.map((v, j) => (
                                                <td
                                                    key={j}
                                                    className={
                                                        typeof v === "number" ? "num" : undefined
                                                    }
                                                >
                                                    {v === null ? (
                                                        <span className="admin-muted">NULL</span>
                                                    ) : (
                                                        renderCell(v)
                                                    )}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                    {result.rows.length === 0 && (
                                        <tr>
                                            <td
                                                className="admin-empty"
                                                colSpan={result.columns.length || 1}
                                            >
                                                No rows
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}

            {history.length > 0 && (
                <>
                    <div className="admin-detail__title">History</div>
                    <ul className="sql-console__history">
                        {history.map((h, i) => (
                            <li key={i}>
                                <button type="button" onClick={() => setSql(h)} title={h}>
                                    {h.replace(/\s+/g, " ")}
                                </button>
                            </li>
                        ))}
                    </ul>
                </>
            )}
        </Tab>
    );
}
