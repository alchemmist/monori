import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api.js";
import { isDemo, useStore } from "./store.js";
import { TABS_KEY } from "./ui/tabPersist.js";

// this Node build ships no localStorage, and the auth/tab paths under test read it
if (!globalThis.localStorage) {
    const data = new Map();
    globalThis.localStorage = {
        getItem: (key) => data.get(key) ?? null,
        setItem: (key, value) => data.set(key, String(value)),
        removeItem: (key) => data.delete(key),
        clear: () => data.clear(),
    };
}

const tab = (id, key, kind = "note") => ({ id, key, kind, props: {} });

beforeEach(() => {
    window.history.replaceState({}, "", "/app");
    localStorage.clear();
    useStore.setState({ user: null, authChecked: false, tabs: [], adminTick: 0 });
});

afterEach(() => {
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
});

describe("isDemo", () => {
    it("matches /demo and its subpaths but nothing else", () => {
        const at = (path) => {
            window.history.replaceState({}, "", path);
            return isDemo();
        };
        expect(at("/demo")).toBe(true);
        expect(at("/demo/")).toBe(true);
        expect(at("/demo///")).toBe(true);
        expect(at("/demo/budget")).toBe(true);
        expect(at("/app")).toBe(false);
        expect(at("/")).toBe(false);
        expect(at("/demonstration")).toBe(false);
        expect(at("/app/demo")).toBe(false);
    });
});

describe("checkAuth", () => {
    it("marks the demo as checked without touching the token or the API", async () => {
        window.history.replaceState({}, "", "/demo");
        const authMe = vi.spyOn(api, "authMe");
        localStorage.setItem("monori_token", "t-1");
        useStore.setState({ tabs: [tab(1, "a")] });

        await useStore.getState().checkAuth();

        expect(authMe).not.toHaveBeenCalled();
        expect(useStore.getState().authChecked).toBe(true);
        expect(useStore.getState().user).toBeNull();
        // the demo never signs anyone out, so restored tabs stay put
        expect(useStore.getState().tabs).toEqual([tab(1, "a")]);
    });

    it("clears restored tabs and skips the API when there is no token", async () => {
        const authMe = vi.spyOn(api, "authMe");
        useStore.setState({ tabs: [tab(1, "a"), tab(2, "b")] });
        localStorage.setItem(TABS_KEY, JSON.stringify([tab(1, "a")]));

        await useStore.getState().checkAuth();

        expect(authMe).not.toHaveBeenCalled();
        expect(useStore.getState().tabs).toEqual([]);
        expect(useStore.getState().authChecked).toBe(true);
        expect(localStorage.getItem(TABS_KEY)).toBe("[]");
    });

    it("adopts the user the token resolves to and keeps the tabs", async () => {
        const authMe = vi.spyOn(api, "authMe").mockResolvedValue({ id: 3, email: "a@b.c" });
        localStorage.setItem("monori_token", "t-1");
        useStore.setState({ tabs: [tab(1, "a")] });

        await useStore.getState().checkAuth();

        expect(authMe).toHaveBeenCalledExactlyOnceWith("t-1");
        expect(useStore.getState().user).toEqual({ id: 3, email: "a@b.c" });
        expect(useStore.getState().authChecked).toBe(true);
        expect(useStore.getState().tabs).toEqual([tab(1, "a")]);
        expect(localStorage.getItem("monori_token")).toBe("t-1");
    });

    it("drops the stale token and the tabs when the token no longer resolves", async () => {
        vi.spyOn(api, "authMe").mockRejectedValue(new Error("401"));
        localStorage.setItem("monori_token", "stale");
        useStore.setState({ user: { id: 3 }, tabs: [tab(1, "a")] });

        await useStore.getState().checkAuth();

        expect(localStorage.getItem("monori_token")).toBeNull();
        expect(useStore.getState().user).toBeNull();
        expect(useStore.getState().authChecked).toBe(true);
        expect(useStore.getState().tabs).toEqual([]);
    });
});

describe("login, register and logout", () => {
    it("stores the issued token and the user it resolves to", async () => {
        const login = vi.spyOn(api, "authLogin").mockResolvedValue({ access_token: "tok" });
        const authMe = vi.spyOn(api, "authMe").mockResolvedValue({ id: 9, email: "a@b.c" });

        await useStore.getState().login("a@b.c", "pw");

        expect(login).toHaveBeenCalledExactlyOnceWith("a@b.c", "pw");
        expect(localStorage.getItem("monori_token")).toBe("tok");
        expect(authMe).toHaveBeenCalledExactlyOnceWith("tok");
        expect(useStore.getState().user).toEqual({ id: 9, email: "a@b.c" });
    });

    it("registers then logs the new account straight in", async () => {
        const register = vi.spyOn(api, "authRegister").mockResolvedValue({});
        const login = vi.spyOn(api, "authLogin").mockResolvedValue({ access_token: "tok2" });
        vi.spyOn(api, "authMe").mockResolvedValue({ id: 10, email: "new@b.c" });

        await useStore.getState().register("new@b.c", "pw");

        expect(register).toHaveBeenCalledExactlyOnceWith("new@b.c", "pw");
        expect(login).toHaveBeenCalledExactlyOnceWith("new@b.c", "pw");
        expect(useStore.getState().user).toEqual({ id: 10, email: "new@b.c" });
    });

    it("propagates a rejected registration without logging in", async () => {
        vi.spyOn(api, "authRegister").mockRejectedValue(new Error("taken"));
        const login = vi.spyOn(api, "authLogin");

        await expect(useStore.getState().register("a@b.c", "pw")).rejects.toThrow("taken");
        expect(login).not.toHaveBeenCalled();
        expect(useStore.getState().user).toBeNull();
    });

    it("wipes the token, the user and the tabs on logout", () => {
        localStorage.setItem("monori_token", "tok");
        useStore.setState({ user: { id: 9 }, tabs: [tab(1, "a"), tab(2, "b")] });

        useStore.getState().logout();

        expect(localStorage.getItem("monori_token")).toBeNull();
        expect(useStore.getState().user).toBeNull();
        expect(useStore.getState().tabs).toEqual([]);
        expect(localStorage.getItem(TABS_KEY)).toBe("[]");
    });
});

describe("tabs", () => {
    it("mirrors every tab write into localStorage", () => {
        useStore.getState().setTabs([tab(4, "x")]);
        expect(useStore.getState().tabs).toEqual([tab(4, "x")]);
        expect(JSON.parse(localStorage.getItem(TABS_KEY))).toEqual([tab(4, "x")]);
    });

    it("appends a tab with rising ids and refuses a duplicate key", () => {
        const s = useStore.getState();
        s.openTab("note", { a: 1 }, "k1");
        const first = useStore.getState().tabs[0];
        expect(first).toMatchObject({ key: "k1", kind: "note", props: { a: 1 } });

        s.openTab("chart", { b: 2 }, "k2");
        const [, second] = useStore.getState().tabs;
        expect(second).toMatchObject({ key: "k2", kind: "chart", props: { b: 2 } });
        expect(second.id).toBe(first.id + 1);

        // same key: the existing tab is kept and no second one is appended
        s.openTab("note", { a: 99 }, "k1");
        expect(useStore.getState().tabs).toEqual([first, second]);
    });

    it("opens keyless tabs side by side and defaults their props to empty", () => {
        const s = useStore.getState();
        s.openTab("note");
        s.openTab("note");
        const tabs = useStore.getState().tabs;
        expect(tabs).toHaveLength(2);
        expect(tabs[0]).toMatchObject({ key: null, kind: "note", props: {} });
        expect(tabs[1].id).toBe(tabs[0].id + 1);
    });

    it("closes only the tab with the given id", () => {
        useStore.setState({ tabs: [tab(1, "a"), tab(2, "b"), tab(3, null)] });
        useStore.getState().closeTab(2);
        expect(useStore.getState().tabs).toEqual([tab(1, "a"), tab(3, null)]);
    });

    it("closes only the tab with the given key", () => {
        useStore.setState({ tabs: [tab(1, "a"), tab(2, "b"), tab(3, "c")] });
        useStore.getState().closeTabByKey("b");
        expect(useStore.getState().tabs).toEqual([tab(1, "a"), tab(3, "c")]);
        expect(JSON.parse(localStorage.getItem(TABS_KEY))).toEqual([tab(1, "a"), tab(3, "c")]);
    });

    it("leaves the tabs alone when no tab carries the key", () => {
        useStore.setState({ tabs: [tab(1, "a"), tab(2, "b")] });
        useStore.getState().closeTabByKey("zzz");
        expect(useStore.getState().tabs).toEqual([tab(1, "a"), tab(2, "b")]);
    });

    it("counts up the admin tick", () => {
        useStore.getState().bumpAdminTick();
        useStore.getState().bumpAdminTick();
        expect(useStore.getState().adminTick).toBe(2);
    });
});
