import { beforeEach, describe, expect, it, vi } from "vitest";
import {
    TABS_KEY,
    TAB_COLLAPSED_KEY,
    loadCollapsed,
    loadTabs,
    saveCollapsed,
    saveTabs,
} from "./tabPersist.js";

const fakeStorage = () => {
    const map = new Map();
    return {
        getItem: (k) => map.get(k) ?? null,
        setItem: (k, v) => map.set(k, String(v)),
        removeItem: (k) => map.delete(k),
    };
};

beforeEach(() => {
    vi.stubGlobal("localStorage", fakeStorage());
});

describe("loadTabs", () => {
    it("round-trips a saved stack", () => {
        const tabs = [{ id: 3, key: "admin-sql", kind: "admin-sql", props: {} }];
        saveTabs(tabs);
        expect(loadTabs()).toEqual(tabs);
    });

    it("is empty with nothing stored", () => {
        expect(loadTabs()).toEqual([]);
    });

    it("survives garbage instead of crashing boot", () => {
        localStorage.setItem(TABS_KEY, "{not json");
        expect(loadTabs()).toEqual([]);
        localStorage.setItem(TABS_KEY, JSON.stringify({ nope: true }));
        expect(loadTabs()).toEqual([]);
    });

    it("drops malformed entries and normalizes a missing key", () => {
        localStorage.setItem(
            TABS_KEY,
            JSON.stringify([
                { id: "x", kind: "admin-sql", props: {} },
                { id: 1, props: {} },
                { id: 2, kind: "migrate" },
                { id: 4, kind: "migrate", props: {}, extra: "dropped" },
            ]),
        );
        expect(loadTabs()).toEqual([{ id: 4, key: null, kind: "migrate", props: {} }]);
    });

    it("keeps a tab's own props", () => {
        saveTabs([{ id: 1, key: "account-edit:7", kind: "account-edit", props: { accountId: 7 } }]);
        expect(loadTabs()[0].props).toEqual({ accountId: 7 });
    });
});

describe("collapsed state", () => {
    it("falls back until the user has toggled the tab", () => {
        expect(loadCollapsed("SQL", false)).toBe(false);
        expect(loadCollapsed("SQL", true)).toBe(true);
        saveCollapsed("SQL", true);
        expect(loadCollapsed("SQL", false)).toBe(true);
    });

    it("keeps tabs apart and ignores a corrupted map", () => {
        saveCollapsed("SQL", true);
        saveCollapsed("Migration", false);
        expect(loadCollapsed("SQL", false)).toBe(true);
        expect(loadCollapsed("Migration", true)).toBe(false);

        localStorage.setItem(TAB_COLLAPSED_KEY, "[]");
        expect(loadCollapsed("SQL", false)).toBe(false);
    });
});
