// One source of truth for how groups and categories are ordered across the app —
// the kanban board, the budget grid and the transaction category picker. Groups
// come first in their own sort order; categories are then listed within each
// group by their own sort. Keying off the group order (not the flat
// category.sort alone) is what makes a group-only reorder — which rewrites only
// group.sort and leaves category.sort untouched — show up everywhere at once.

// match the backend's ORDER BY sort, id — deterministic even when sort is
// missing (demo groups omit it) or tied
export const bySortThenId = (a, b) => (a.sort ?? 0) - (b.sort ?? 0) || a.id - b.id;

export function orderedGroups(snapshot) {
    return [...(snapshot.groups ?? [])].sort(bySortThenId);
}

export function categoriesByGroup(snapshot, groups = orderedGroups(snapshot)) {
    const m = new Map(groups.map((g) => [g.id, []]));
    for (const c of [...(snapshot.categories ?? [])].sort(bySortThenId)) {
        if (m.has(c.groupId)) m.get(c.groupId).push(c);
    }
    return m;
}
