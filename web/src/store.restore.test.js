import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The restored-tabs seeding runs once, at store module load, so each case here
 * imports a fresh store module against its own stubbed persistence layer.
 */
async function storeWith(restored) {
    vi.resetModules();
    vi.doMock("./ui/tabPersist.js", () => ({
        loadTabs: () => restored,
        saveTabs: () => {},
    }));
    const { useStore } = await import("./store.js");
    return useStore;
}

afterEach(() => {
    vi.doUnmock("./ui/tabPersist.js");
    vi.resetModules();
});

describe("tab ids across a reload", () => {
    it("adopts the restored tabs as the starting state", async () => {
        const restored = [{ id: 4, key: "a", kind: "note", props: {} }];
        const useStore = await storeWith(restored);
        expect(useStore.getState().tabs).toEqual(restored);
    });

    it("issues ids past the highest restored one, not past the last one", async () => {
        // the highest id sits in the middle: a reducer that tracked the minimum
        // or the last element would reissue 8 and collide
        const useStore = await storeWith([
            { id: 3, key: "a", kind: "note", props: {} },
            { id: 8, key: "b", kind: "note", props: {} },
            { id: 5, key: "c", kind: "note", props: {} },
        ]);

        useStore.getState().openTab("note", {}, "new");

        expect(useStore.getState().tabs.at(-1).id).toBe(9);
    });

    it("starts at one when nothing came back from storage", async () => {
        const useStore = await storeWith([]);
        useStore.getState().openTab("note", {}, "new");
        expect(useStore.getState().tabs).toEqual([{ id: 1, key: "new", kind: "note", props: {} }]);
    });
});
