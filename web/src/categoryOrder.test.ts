import { describe, expect, it } from "vitest";
import { bySortThenId, categoriesByGroup, orderedGroups } from "./categoryOrder.js";

describe("bySortThenId", () => {
    it("orders by sort first", () => {
        expect(bySortThenId({ id: 9, sort: 1 }, { id: 1, sort: 2 })).toBeLessThan(0);
    });

    it("breaks ties on id", () => {
        expect(bySortThenId({ id: 5, sort: 3 }, { id: 2, sort: 3 })).toBeGreaterThan(0);
    });

    // demo groups carry no sort at all, so the comparator must not go NaN — and
    // the fill-in has to be 0 on *both* sides, or a sortless item silently
    // outranks (or is outranked by) a real sort: 0 item
    it("treats a missing sort as zero on either side", () => {
        expect(bySortThenId({ id: 1 }, { id: 2, sort: 1 })).toBe(-1);
        expect(bySortThenId({ id: 4 }, { id: 2 })).toBe(2);
        // a missing sort ties with an explicit 0, so the id alone decides
        expect(bySortThenId({ id: 1 }, { id: 2, sort: 0 })).toBe(-1);
        expect(bySortThenId({ id: 2, sort: 0 }, { id: 1 })).toBe(1);
        // and it must lose to a negative sort, not win by an off-by-one default
        expect(bySortThenId({ id: 1 }, { id: 2, sort: -1 })).toBeGreaterThan(0);
        expect(bySortThenId({ id: 2, sort: -1 }, { id: 1 })).toBeLessThan(0);
    });
});

describe("orderedGroups", () => {
    it("returns a sorted copy without touching the input", () => {
        const input = [
            { id: 2, sort: 3 },
            { id: 1, sort: 1 },
        ];
        const out = orderedGroups(input);
        expect(out.map((g) => g.id)).toEqual([1, 2]);
        expect(input.map((g) => g.id)).toEqual([2, 1]);
        expect(out).not.toBe(input);
    });

    it("survives a missing list", () => {
        expect(orderedGroups(undefined)).toEqual([]);
    });
});

describe("categoriesByGroup", () => {
    const groups = [
        { id: 1, sort: 1 },
        { id: 2, sort: 2 },
    ];

    it("buckets categories per group, each in its own sort order", () => {
        const cats = [
            { id: 10, groupId: 2, sort: 2 },
            { id: 11, groupId: 1, sort: 5 },
            { id: 12, groupId: 2, sort: 1 },
            { id: 13, groupId: 1, sort: 1 },
        ];
        const m = categoriesByGroup(cats, groups);
        expect([...m.keys()]).toEqual([1, 2]);
        expect(m.get(1)!.map((c) => c.id)).toEqual([13, 11]);
        expect(m.get(2)!.map((c) => c.id)).toEqual([12, 10]);
    });

    it("keeps the given group order, not the group sort", () => {
        const m = categoriesByGroup([], [groups[1]!, groups[0]!]);
        expect([...m.keys()]).toEqual([2, 1]);
    });

    // the budget grid passes an expense-only subset and must not get the rest
    it("drops categories whose group was not passed in", () => {
        const m = categoriesByGroup([{ id: 10, groupId: 99, sort: 1 }], groups);
        expect(m.get(1)).toEqual([]);
        expect(m.get(2)).toEqual([]);
    });

    it("gives every group an empty bucket when there are no categories", () => {
        const m = categoriesByGroup(undefined, groups);
        expect(m.get(1)).toEqual([]);
    });
});
