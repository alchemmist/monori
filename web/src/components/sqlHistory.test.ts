import { beforeEach, describe, expect, it, vi } from "vitest";
import { HISTORY_KEY, HISTORY_MAX, loadHistory, remember } from "./sqlHistory.js";

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

describe("sql console history", () => {
    it("keeps the most recent query first", () => {
        remember("SELECT 1");
        expect(remember("SELECT 2")).toEqual(["SELECT 2", "SELECT 1"]);
        expect(loadHistory()).toEqual(["SELECT 2", "SELECT 1"]);
    });

    it("moves a re-run query back to the top instead of duplicating it", () => {
        remember("SELECT 1");
        remember("SELECT 2");
        expect(remember("SELECT 1")).toEqual(["SELECT 1", "SELECT 2"]);
    });

    it("caps the list", () => {
        for (let i = 0; i <= HISTORY_MAX + 5; i++) remember(`SELECT ${i}`);
        const history = loadHistory();
        expect(history).toHaveLength(HISTORY_MAX);
        expect(history[0]).toBe(`SELECT ${HISTORY_MAX + 5}`);
    });

    it("survives junk in storage", () => {
        localStorage.setItem(HISTORY_KEY, "{not json");
        expect(loadHistory()).toEqual([]);
        localStorage.setItem(HISTORY_KEY, JSON.stringify(["ok", 42, null]));
        expect(loadHistory()).toEqual(["ok"]);
    });

    it("still returns the new history when storage refuses the write", () => {
        vi.stubGlobal("localStorage", {
            getItem: () => null,
            setItem: () => {
                throw new Error("QuotaExceededError");
            },
        });
        expect(remember("SELECT 1")).toEqual(["SELECT 1"]);
    });
});
