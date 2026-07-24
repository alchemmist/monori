import { useId, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { ChevronLeft, ChevronRight, Xmark } from "@gravity-ui/icons";

/**
 * Tab — a dockable side panel that behaves like a real tab: it pins to the
 * right edge, collapses to a labeled strip and expands back, and the app stays
 * interactive behind it. Open tabs form a stack of cards along the right edge
 * (mount order: the first tab sits at the edge, later ones line up to its
 * left); collapsing one reflows the rest, since a collapsed tab only occupies
 * its strip width.
 *
 * Props:
 *  - title:      header text of the expanded tab
 *  - strip:      short label shown vertically on the collapsed strip
 *  - onClose:    called when the user closes the tab
 *  - footer:     optional node rendered pinned to the bottom (actions)
 *  - defaultCollapsed: start collapsed (default false)
 */

export const TAB_WIDTH = 420;
export const TAB_STRIP_WIDTH = 34;

// module-level registry of mounted tabs so each one knows its offset from the
// right edge; a context provider would demand wrapping the app for what is a
// handful of fixed-position elements
const stack = {
    tabs: [], // [{id, width}] in mount order
    listeners: new Set(),
};

function emit() {
    for (const fn of stack.listeners) fn();
}

function subscribe(fn) {
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

function registerTab(id, width) {
    stack.tabs = [...stack.tabs, { id, width }];
    emit();
}

function resizeTab(id, width) {
    stack.tabs = stack.tabs.map((t) => (t.id === id ? { ...t, width } : t));
    emit();
}

function unregisterTab(id) {
    stack.tabs = stack.tabs.filter((t) => t.id !== id);
    emit();
}

export default function Tab({ title, strip, onClose, footer, defaultCollapsed = false, children }) {
    const id = useId();
    const ref = useRef(null);
    const [collapsed, setCollapsed] = useState(defaultCollapsed);
    const [animating, setAnimating] = useState(false);

    // register before paint (so co-mounting tabs never flash overlapped) with
    // the real rendered width — CSS caps the tab at 92vw, so the 420px constant
    // can overstate the slot on narrow viewports; a ResizeObserver keeps the
    // slot honest through collapse/expand transitions and window resizes
    useLayoutEffect(() => {
        registerTab(id, ref.current?.offsetWidth ?? TAB_WIDTH);
        const ro = new ResizeObserver(() => {
            if (ref.current) resizeTab(id, ref.current.offsetWidth);
        });
        if (ref.current) ro.observe(ref.current);
        return () => {
            ro.disconnect();
            unregisterTab(id);
        };
    }, [id]);

    const offset = useSyncExternalStore(subscribe, () => computeOffset(stack.tabs, id));

    const toggle = (next) => {
        setCollapsed(next);
        setAnimating(true);
    };

    const cls = ["ui-tab", collapsed && "ui-tab_collapsed", animating && "ui-tab_animating"]
        .filter(Boolean)
        .join(" ");

    return (
        <aside
            ref={ref}
            className={cls}
            style={{ right: offset }}
            onTransitionEnd={(e) => {
                if (e.propertyName === "width") setAnimating(false);
            }}
        >
            <button
                type="button"
                className="ui-tab__strip"
                onClick={() => toggle(false)}
                title={`Expand ${strip || title}`}
                aria-label={`Expand ${strip || title}`}
                aria-hidden={!collapsed}
                tabIndex={collapsed ? 0 : -1}
            >
                <ChevronLeft width={16} height={16} />
                <span className="ui-tab__strip-label">{strip || title}</span>
            </button>
            <div className="ui-tab__inner">
                <div className="ui-tab__head">
                    <div className="ui-tab__title">{title}</div>
                    <div className="ui-tab__head-actions">
                        <button
                            type="button"
                            className="ui-tab__icon-btn"
                            onClick={() => toggle(true)}
                            title="Collapse — the app stays usable behind the tab"
                            aria-label={`Collapse ${strip || title}`}
                        >
                            <ChevronRight width={16} height={16} />
                        </button>
                        <button
                            type="button"
                            className="ui-tab__icon-btn"
                            onClick={onClose}
                            title="Close"
                            aria-label={`Close ${strip || title}`}
                        >
                            <Xmark width={16} height={16} />
                        </button>
                    </div>
                </div>
                <div className="ui-tab__content">{children}</div>
                {footer && <div className="ui-tab__footer">{footer}</div>}
            </div>
        </aside>
    );
}
