import { beforeEach, describe, expect, it, vi } from "vitest";
import {
    TABS_KEY,
    TAB_COLLAPSED_KEY,
    TAB_WIDTH_KEY,
    loadCollapsed,
    loadTabs,
    loadWidth,
    saveCollapsed,
    saveTabs,
    saveWidth,
} from "./tabPersist.js";

const fakeStorage = () => {
    const map = new Map<string, string>();
    return {
        getItem: (k: string) => map.get(k) ?? null,
        setItem: (k: string, v: string) => map.set(k, String(v)),
        removeItem: (k: string) => map.delete(k),
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

    it("falls back when storage itself throws while reading", () => {
        vi.stubGlobal("localStorage", {
            getItem: () => {
                throw new Error("blocked");
            },
        });
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
        expect(loadTabs()[0]!.props).toEqual({ accountId: 7 });
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

describe("dragged width", () => {
    it("remembers a drag per tab and rounds it to whole pixels", () => {
        expect(loadWidth("SQL", null)).toBe(null);
        saveWidth("SQL", 733.4);
        saveWidth("Migration", 420);
        expect(loadWidth("SQL", null)).toBe(733);
        expect(loadWidth("Migration", null)).toBe(420);
    });

    it("resets to the tab's own width when saved as null", () => {
        saveWidth("SQL", 900);
        saveWidth("SQL", null);
        expect(loadWidth("SQL", null)).toBe(null);
    });

    it("ignores a corrupted map or a nonsense width", () => {
        localStorage.setItem(TAB_WIDTH_KEY, "[]");
        expect(loadWidth("SQL", 420)).toBe(420);
        localStorage.setItem(TAB_WIDTH_KEY, JSON.stringify({ SQL: "wide", Migration: -5 }));
        expect(loadWidth("SQL", 420)).toBe(420);
        expect(loadWidth("Migration", 420)).toBe(420);
    });

    it("accepts only finite positive numeric widths", () => {
        // NaN and Infinity cannot survive JSON.stringify (they serialize to null),
        // so route the parse through a stub to actually reach loadWidth's
        // Number.isFinite guard with real non-finite numbers.
        localStorage.setItem(TAB_WIDTH_KEY, "{}");
        vi.spyOn(JSON, "parse").mockReturnValue({
            nan: NaN,
            infinite: Infinity,
            text: "300",
            zero: 0,
            negative: -5,
            ok: 300,
        });
        expect(loadWidth("nan", 420)).toBe(420);
        expect(loadWidth("infinite", 420)).toBe(420);
        expect(loadWidth("text", 420)).toBe(420);
        expect(loadWidth("zero", 420)).toBe(420);
        expect(loadWidth("negative", 420)).toBe(420);
        expect(loadWidth("ok", 420)).toBe(300);
    });
});
