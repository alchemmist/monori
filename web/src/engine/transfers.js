/**
 * Transfers as the ledger sees them — pure functions, no I/O.
 *
 * In the database a transfer is still two transactions; the `transfers` entity
 * only says the two belong together. Everything downstream needs one of two
 * views of that: the analytics and budget engines want the legs to disappear,
 * and the transactions table wants them collapsed into a single row.
 */

/** The one place that decides a transaction is part of a transfer. Moving money
 * between your own accounts is neither income nor spending, so every total that
 * is about income or spending has to ask this first. */
export function isTransfer(t) {
    return t.transferId != null;
}

/**
 * Collapse the legs of each transfer in `rows` into one item.
 *
 * `rows` is the visible (already filtered and sorted) list; `all` is every
 * transaction the snapshot holds, because a filter can hide one leg while the
 * other stays on screen and the merged row still needs both sides to say where
 * the money went.
 *
 * Returns items of three shapes:
 *   {kind: "tx", key, tx}
 *   {kind: "transfer", key, transferId, out, in: inLeg, amount}
 *   {kind: "leg", key, tx}          — a leg of an expanded transfer
 * A transfer takes the position of whichever leg came first in `rows`. A leg
 * whose partner is missing from `all` (the ledger loads newest-first, so an old
 * partner may not have streamed in yet) stays an ordinary row.
 *
 * `expanded` is the set of transfer ids the user has opened up; their legs are
 * emitted right after the merged row. Every item is one table row of the same
 * height, which is what lets the caller keep windowing on a fixed row height.
 */
export function mergeTransferRows(rows, all = rows, expanded = new Set()) {
    const legs = new Map();
    for (const t of all) {
        if (!isTransfer(t)) continue;
        const pair = legs.get(t.transferId) ?? [];
        pair.push(t);
        legs.set(t.transferId, pair);
    }

    const emitted = new Set();
    const items = [];
    for (const t of rows) {
        if (!isTransfer(t)) {
            items.push({ kind: "tx", key: `t${t.id}`, tx: t });
            continue;
        }
        if (emitted.has(t.transferId)) continue;
        const pair = legs.get(t.transferId) ?? [];
        const out = pair.find((leg) => leg.amount < 0);
        const inLeg = pair.find((leg) => leg.amount > 0);
        if (pair.length !== 2 || !out || !inLeg) {
            items.push({ kind: "tx", key: `t${t.id}`, tx: t });
            continue;
        }
        emitted.add(t.transferId);
        items.push({
            kind: "transfer",
            key: `x${t.transferId}`,
            transferId: t.transferId,
            out,
            in: inLeg,
            amount: inLeg.amount,
        });
        if (expanded.has(t.transferId)) {
            items.push({ kind: "leg", key: `l${out.id}`, tx: out });
            items.push({ kind: "leg", key: `l${inLeg.id}`, tx: inLeg });
        }
    }
    return items;
}

/** The date a merged row shows: the outgoing leg's, since that is when the
 * money left. Both legs' dates are handed back so the row can say so when the
 * bank posted them on different days. */
export function transferDates(item) {
    const from = item.out.date.slice(0, 10);
    const to = item.in.date.slice(0, 10);
    return { date: item.out.date, sameDay: from === to };
}
