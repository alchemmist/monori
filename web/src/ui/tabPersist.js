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

function read(key, fallback) {
    try {
        const raw = store()?.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
    } catch {
        return fallback;
    }
}

function write(key, value) {
    try {
        store()?.setItem(key, JSON.stringify(value));
    } catch {
        // a full or blocked storage only costs persistence, never the session
    }
}

const isPlainObject = (v) => typeof v === "object" && v !== null && !Array.isArray(v);

/** Restored tabs, with anything malformed dropped rather than crashing boot. */
export function loadTabs() {
    const raw = read(TABS_KEY, []);
    if (!Array.isArray(raw)) return [];
    return raw
        .filter(
            (t) =>
                isPlainObject(t) &&
                typeof t.id === "number" &&
                typeof t.kind === "string" &&
                isPlainObject(t.props),
        )
        .map((t) => ({ id: t.id, key: t.key ?? null, kind: t.kind, props: t.props }));
}

export function saveTabs(tabs) {
    write(TABS_KEY, tabs);
}

/** Collapsed flags keyed by a tab's stable persistence key (see Tab.jsx). */
export function loadCollapsed(key, fallback) {
    const map = read(TAB_COLLAPSED_KEY, {});
    if (!isPlainObject(map) || typeof map[key] !== "boolean") return fallback;
    return map[key];
}

export function saveCollapsed(key, collapsed) {
    const map = read(TAB_COLLAPSED_KEY, {});
    write(TAB_COLLAPSED_KEY, { ...(isPlainObject(map) ? map : {}), [key]: collapsed });
}

/** Dragged widths in px, keyed the same way; the viewport cap stays in CSS. */
export function loadWidth(key, fallback) {
    const map = read(TAB_WIDTH_KEY, {});
    if (!isPlainObject(map)) return fallback;
    const w = map[key];
    return typeof w === "number" && Number.isFinite(w) && w > 0 ? w : fallback;
}

export function saveWidth(key, width) {
    const map = read(TAB_WIDTH_KEY, {});
    const next = { ...(isPlainObject(map) ? map : {}) };
    // null resets the tab to whatever width its own props ask for
    if (width == null) delete next[key];
    else next[key] = Math.round(width);
    write(TAB_WIDTH_KEY, next);
}
