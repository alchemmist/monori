/* Query history for the admin SQL console — per browser, deliberately not on
 * the server: it is a convenience for retyping, not shared state. Kept out of
 * the component so it can be exercised without a DOM. */

export const HISTORY_KEY = "monori_sql_history";
export const HISTORY_MAX = 30;

export function loadHistory() {
    try {
        const raw = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
        return Array.isArray(raw) ? raw.filter((s) => typeof s === "string") : [];
    } catch {
        return [];
    }
}

/** Most recent first, deduplicated: re-running a query moves it back to the top. */
export function remember(sql) {
    const next = [sql, ...loadHistory().filter((s) => s !== sql)].slice(0, HISTORY_MAX);
    try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
    } catch {
        /* private mode or quota — losing history must never lose the result */
    }
    return next;
}
