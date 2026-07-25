import { useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { ChevronLeft, ChevronRight, Xmark } from "@gravity-ui/icons";
import {
    TAB_WIDTH,
    offsetOf,
    registerTab,
    resizeTab,
    subscribe,
    unregisterTab,
} from "./tabStack.js";

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
 *  - width:      expanded width as a percentage of the viewport, for tabs that
 *                need more than the default 420px card (the SQL console asks
 *                for 60). CSS still caps it at 92vw so the app stays visible.
 */

export default function Tab({
    title,
    strip,
    onClose,
    footer,
    defaultCollapsed = false,
    width,
    children,
}) {
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

    const offset = useSyncExternalStore(subscribe, () => offsetOf(id));

    const toggle = (next) => {
        setCollapsed(next);
        setAnimating(true);
    };

    // `animating` gates pointer input; transitionend can be missed entirely
    // (reduced motion, interrupted/overridden transition), so never leave the
    // tab inert longer than the 0.25s transition could possibly last
    useEffect(() => {
        if (!animating) return undefined;
        const t = setTimeout(() => setAnimating(false), 400);
        return () => clearTimeout(t);
    }, [animating]);

    const cls = ["ui-tab", collapsed && "ui-tab_collapsed", animating && "ui-tab_animating"]
        .filter(Boolean)
        .join(" ");

    return (
        <aside
            ref={ref}
            className={cls}
            style={{ right: offset, ...(width ? { "--ui-tab-w": `${width}vw` } : null) }}
            onTransitionEnd={(e) => {
                if (e.propertyName === "width") setAnimating(false);
            }}
            onTransitionCancel={(e) => {
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
            {/* collapsed content is only clipped visually — inert keeps keyboard
                focus and assistive tech out of the invisible controls */}
            <div className="ui-tab__inner" inert={collapsed || undefined}>
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
