/**
 * Module-level registry of mounted tabs so each one knows its offset from the
 * right edge; a context provider would demand wrapping the app for what is a
 * handful of fixed-position elements. Lives outside Tab.jsx so the component
 * file only exports components (fast refresh).
 */

export const TAB_WIDTH = 420;
export const TAB_STRIP_WIDTH = 34;

interface StackTab {
    id: string | number;
    width: number;
}

const stack = {
    tabs: [] as StackTab[], // [{id, width}] in mount order
    listeners: new Set<() => void>(),
};

function emit() {
    for (const fn of stack.listeners) fn();
}

export function subscribe(fn: () => void) {
    stack.listeners.add(fn);
    return () => stack.listeners.delete(fn);
}

/** Right-edge offset of tab `id`: earlier-mounted tabs sit at the edge, so a
 * later tab is pushed left by the summed widths of everything before it. */
export function computeOffset(tabs: StackTab[], id: string | number) {
    let offset = 0;
    for (const t of tabs) {
        if (t.id === id) return offset;
        offset += t.width;
    }
    return offset;
}

export function offsetOf(id: string | number) {
    return computeOffset(stack.tabs, id);
}

/** Layer tabs like overlapping cards: the one nearest the right edge (mounted
 * first) stays above the tabs pushed to its left, so its left-facing shadow
 * falls onto the neighbouring card instead of disappearing beneath it. */
function computeLayer(tabs: StackTab[], id: string | number) {
    const index = tabs.findIndex((tab) => tab.id === id);
    return index < 0 ? 0 : tabs.length - index;
}

export function layerOf(id: string | number) {
    return computeLayer(stack.tabs, id);
}

export function registerTab(id: string | number, width: number) {
    stack.tabs = [...stack.tabs, { id, width }];
    emit();
}

export function resizeTab(id: string | number, width: number) {
    stack.tabs = stack.tabs.map((t) => (t.id === id ? { ...t, width } : t));
    emit();
}

export function unregisterTab(id: string | number) {
    stack.tabs = stack.tabs.filter((t) => t.id !== id);
    emit();
}
