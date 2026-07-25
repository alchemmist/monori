/** The canonical ledger order, matching the server's `ORDER BY date, id`. */
export const compareTx = (a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id - b.id);

/**
 * Merge a background chunk into the loaded ledger. Both sides are expected in
 * canonical order and the result stays in it, so views never see a half-sorted
 * list. Rows already present win: a chunk that arrives after an optimistic
 * local edit must not resurrect the stale server copy.
 */
export function mergeTransactions(existing, incoming) {
    if (!incoming.length) return existing;
    if (!existing.length) return [...incoming];
    const seen = new Set(existing.map((t) => t.id));
    const fresh = incoming.filter((t) => !seen.has(t.id));
    if (!fresh.length) return existing;
    const out = [];
    let i = 0;
    let j = 0;
    while (i < existing.length && j < fresh.length) {
        out.push(compareTx(fresh[j], existing[i]) < 0 ? fresh[j++] : existing[i++]);
    }
    while (i < existing.length) out.push(existing[i++]);
    while (j < fresh.length) out.push(fresh[j++]);
    return out;
}
