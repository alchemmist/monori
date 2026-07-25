/**
 * Module-level registry of mounted tabs so each one knows its offset from the
 * right edge; a context provider would demand wrapping the app for what is a
 * handful of fixed-position elements. Lives outside Tab.jsx so the component
 * file only exports components (fast refresh).
 */

export const TAB_WIDTH = 420;
export const TAB_STRIP_WIDTH = 34;

const stack = {
    tabs: [], // [{id, width}] in mount order
    listeners: new Set(),
};

function emit() {
    for (const fn of stack.listeners) fn();
}

export function subscribe(fn) {
    stack.listeners.add(fn);
    return () => stack.listeners.delete(fn);
}

/** Right-edge offset of tab `id`: earlier-mounted tabs sit at the edge, so a
 * later tab is pushed left by the summed widths of everything before it. */
export function computeOffset(tabs, id) {
    let offset = 0;
    for (const t of tabs) {
        if (t.id === id) return offset;
        offset += t.width;
    }
    return offset;
}

export function offsetOf(id) {
    return computeOffset(stack.tabs, id);
}

export function registerTab(id, width) {
    stack.tabs = [...stack.tabs, { id, width }];
    emit();
}

export function resizeTab(id, width) {
    stack.tabs = stack.tabs.map((t) => (t.id === id ? { ...t, width } : t));
    emit();
}

export function unregisterTab(id) {
    stack.tabs = stack.tabs.filter((t) => t.id !== id);
    emit();
}
