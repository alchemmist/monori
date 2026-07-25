/**
 * Union two keyword lists the way the server does: case-insensitive dedupe,
 * target's own keys first, order otherwise preserved.
 */
export function unionKeywords(a, b) {
    const seen = new Set();
    const out = [];
    for (const raw of [...String(a ?? "").split("|"), ...String(b ?? "").split("|")]) {
        const kw = raw.trim();
        const key = kw.toLowerCase();
        if (kw && !seen.has(key)) {
            seen.add(key);
            out.push(kw);
        }
    }
    return out.join("|");
}

/**
 * Apply a category merge to a snapshot, mirroring POST /categories/{id}/merge:
 * transactions move to the target, keywords are unioned, budgets are summed per
 * month, the source disappears. Budgets are summed rather than dropped because
 * the spending moves across too — losing the plan would fake a retroactive
 * overspend on the target.
 */
export function mergeCategories(snapshot, sourceId, targetId) {
    if (sourceId === targetId) return snapshot;
    const source = snapshot.categories.find((c) => c.id === sourceId);
    const target = snapshot.categories.find((c) => c.id === targetId);
    if (!source || !target) return snapshot;

    const budgets = snapshot.budgets
        .filter((b) => b.categoryId !== sourceId)
        .map((b) => ({ ...b }));
    const byMonth = new Map(
        budgets.filter((b) => b.categoryId === targetId).map((b) => [`${b.year}-${b.month}`, b]),
    );
    for (const b of snapshot.budgets) {
        if (b.categoryId !== sourceId) continue;
        const hit = byMonth.get(`${b.year}-${b.month}`);
        if (hit) hit.amount += b.amount;
        else budgets.push({ ...b, categoryId: targetId });
    }

    return {
        ...snapshot,
        categories: snapshot.categories
            .filter((c) => c.id !== sourceId)
            .map((c) =>
                c.id === targetId
                    ? { ...c, keywords: unionKeywords(c.keywords, source.keywords) }
                    : c,
            ),
        budgets,
        transactions: snapshot.transactions.map((t) =>
            t.categoryId === sourceId ? { ...t, categoryId: targetId } : t,
        ),
    };
}
