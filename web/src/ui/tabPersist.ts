/**
 * Persistence for the docked tabs: which tabs are open, whether each one is
 * collapsed and how wide the user dragged it. Written once here so every
 * current and future tab survives a reload without its call site opting in —
 * openTab/closeTab in the store and the collapse/resize handlers in Tab.jsx are
 * the only places that touch it.
 *
 * Tab props therefore have to be JSON-serializable; anything that isn't (a
 * callback, a DOM node) is dropped by the round-trip, so tabs pass ids and
 * plain data and read the live object out of the snapshot.
 */

export const TABS_KEY = "monori_tabs";
export const TAB_COLLAPSED_KEY = "monori_tab_collapsed";
export const TAB_WIDTH_KEY = "monori_tab_width";

const store = () => (typeof localStorage === "undefined" ? null : localStorage);

function read(key: string, fallback: unknown): unknown {
    try {
        const raw = store()?.getItem(key);
        return raw == null || raw === "" ? fallback : (JSON.parse(raw) as unknown);
    } catch {
        return fallback;
    }
}

function write(key: string, value: unknown) {
    try {
        store()?.setItem(key, JSON.stringify(value));
    } catch {
        // a full or blocked storage only costs persistence, never the session
    }
}

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
    typeof value === "object" && value !== null && !Array.isArray(value);

type RestoredTab = {
    id: number;
    key?: string;
    kind: string;
    props: Record<string, unknown>;
};

const isRestoredTab = (value: unknown): value is RestoredTab =>
    isPlainObject(value) &&
    typeof value["id"] === "number" &&
    (value["key"] === undefined || typeof value["key"] === "string") &&
    typeof value["kind"] === "string" &&
    isPlainObject(value["props"]);

/** Restored tabs, with anything malformed dropped rather than crashing boot. */
export function loadTabs(): TabDescriptor[] {
    const raw = read(TABS_KEY, []);
    if (!Array.isArray(raw)) return [];
    return raw.filter(isRestoredTab).map((t) => ({
        id: t.id,
        key: t.key ?? null,
        kind: t.kind,
        props: t.props,
    }));
}

export function saveTabs(tabs: TabDescriptor[]) {
    write(TABS_KEY, tabs);
}

/** Collapsed flags keyed by a tab's stable persistence key (see Tab.jsx). */
export function loadCollapsed(key: string, fallback: boolean): boolean {
    const map = read(TAB_COLLAPSED_KEY, {});
    if (!isPlainObject(map) || typeof map[key] !== "boolean") return fallback;
    return map[key];
}

export function saveCollapsed(key: string, collapsed: boolean) {
    const map = read(TAB_COLLAPSED_KEY, {});
    write(TAB_COLLAPSED_KEY, { ...(isPlainObject(map) ? map : {}), [key]: collapsed });
}

/** Dragged widths in px, keyed the same way; the viewport cap stays in CSS. */
export function loadWidth(key: string, fallback: number | null): number | null {
    const map = read(TAB_WIDTH_KEY, {});
    if (!isPlainObject(map)) return fallback;
    const w = map[key];
    return typeof w === "number" && Number.isFinite(w) && w > 0 ? w : fallback;
}

export function saveWidth(key: string, width: number | null) {
    const map = read(TAB_WIDTH_KEY, {});
    const next = { ...(isPlainObject(map) ? map : {}) };
    // null resets the tab to whatever width its own props ask for
    if (width == null) Reflect.deleteProperty(next, key);
    else next[key] = Math.round(width);
    write(TAB_WIDTH_KEY, next);
}
import type { TabDescriptor } from "../types.js";
