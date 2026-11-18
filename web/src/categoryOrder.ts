// One source of truth for how groups and categories are ordered across the app —
// the kanban board, the budget grid and the transaction category picker. Groups
// come first in their own sort order; categories are then listed within each
// group by their own sort. Keying off the group order (not the flat
// category.sort alone) is what makes a group-only reorder — which rewrites only
// group.sort and leaves category.sort untouched — show up everywhere at once.

// match the backend's ORDER BY sort, id — deterministic even when sort is
// missing (demo groups omit it) or tied
type Sortable = { id: number; sort?: number };

export const bySortThenId = (a: Sortable, b: Sortable): number =>
    (a.sort ?? 0) - (b.sort ?? 0) || a.id - b.id;

export function orderedGroups<T extends Sortable>(groups: T[] | null | undefined): T[] {
    return [...(groups ?? [])].sort(bySortThenId);
}

// `groups` must already be in order (pass the result of orderedGroups); the map
// preserves that order and only fills groups it was given, so callers can scope
// to a subset (e.g. the budget grid's expense-only groups)
export function categoriesByGroup<T extends Sortable & { groupId: number }>(
    categories: T[] | null | undefined,
    groups: Sortable[],
): Map<number, T[]> {
    const m = new Map(groups.map((group) => [group.id, [] as T[]]));
    for (const c of [...(categories ?? [])].sort(bySortThenId)) {
        m.get(c.groupId)?.push(c);
    }
    return m;
}
