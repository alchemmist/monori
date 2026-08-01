import { useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import { ChevronLeft, ChevronRight, Xmark } from "@gravity-ui/icons";
import {
    TAB_WIDTH,
    layerOf,
    offsetOf,
    registerTab,
    resizeTab,
    subscribe,
    unregisterTab,
} from "./tabStack.js";
import { loadCollapsed, loadWidth, saveCollapsed, saveWidth } from "./tabPersist.js";

interface TabProps {
    title: ReactNode;
    strip?: string;
    onClose: () => void;
    footer?: ReactNode;
    defaultCollapsed?: boolean;
    persistKey?: string;
    width?: number;
    children: ReactNode;
}

type TabStyle = CSSProperties & { "--ui-tab-w"?: string };

// a dragged tab stays between a tenth and nine tenths of the viewport: never so
// narrow it is unreadable, never so wide the app behind it is gone
const MIN_TAB_RATIO = 0.1;
const MAX_TAB_RATIO = 0.9;

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
 *  - defaultCollapsed: start collapsed the first time (default false); after
 *                that the user's own collapse/expand is remembered
 *  - persistKey: storage key for that remembered state, defaulting to the strip
 *                label; give it an explicit value when several tabs of one kind
 *                can be open at once and should be remembered apart
 *  - width:      default expanded width as a percentage of the viewport, for
 *                tabs that need more than the default 420px card (the SQL
 *                console asks for 60). CSS still caps it at 90vw so the app
 *                stays visible.
 *
 * Every tab can be resized by dragging its left edge, between a tenth and nine
 * tenths of the viewport; the width is remembered under the same persistKey, so
 * the drag survives a reload and no call site has to opt in.
 *
 * Which tabs are open is persisted centrally by the store (see ui/tabPersist.js),
 * so a reload restores the stack without any tab having to ask for it.
 */

export default function Tab({
    title,
    strip = typeof title === "string" ? title : "Tab",
    onClose,
    footer,
    defaultCollapsed = false,
    persistKey,
    width,
    children,
}: TabProps) {
    const id = useId();
    const ref = useRef<HTMLElement>(null);
    const stateKey = persistKey ?? strip;
    const accessibleTitle = strip || (typeof title === "string" ? title : "Tab");
    const [collapsed, setCollapsed] = useState(() => loadCollapsed(stateKey, defaultCollapsed));
    const [animating, setAnimating] = useState(false);
    // null means "never dragged" — the tab then keeps whatever width its own
    // `width` prop (or the CSS default) asks for
    const [dragged, setDragged] = useState(() => loadWidth(stateKey, null));
    const [resizing, setResizing] = useState(false);

    // register before paint (so co-mounting tabs never flash overlapped) with
    // the real rendered width — CSS caps the tab at 90vw, so the 420px constant
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
    const layer = useSyncExternalStore(subscribe, () => layerOf(id));

    // closing the tab mid-drag must not leave the page unselectable
    useEffect(
        () => () => {
            document.body.style.userSelect = "";
            document.body.style.cursor = "";
        },
        [],
    );

    const toggle = (next: boolean) => {
        setCollapsed(next);
        saveCollapsed(stateKey, next);
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

    // dragging the left edge: the tab is pinned right, so pulling the pointer
    // left by N px widens it by N; the width transition is dropped mid-drag so
    // the edge tracks the cursor instead of lagging a quarter second behind
    const startResize = (e: ReactPointerEvent<HTMLDivElement>) => {
        if (collapsed) return;
        e.preventDefault();
        const startX = e.clientX;
        const startW = ref.current?.offsetWidth ?? TAB_WIDTH;
        const min = window.innerWidth * MIN_TAB_RATIO;
        const max = window.innerWidth * MAX_TAB_RATIO;
        let next = startW;
        setResizing(true);
        e.currentTarget.setPointerCapture(e.pointerId);
        document.body.style.userSelect = "none";
        document.body.style.cursor = "ew-resize";

        const move = (ev: PointerEvent) => {
            next = Math.min(Math.max(startW + (startX - ev.clientX), min), max);
            setDragged(next);
        };
        const stop = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", stop);
            window.removeEventListener("pointercancel", stop);
            document.body.style.userSelect = "";
            document.body.style.cursor = "";
            setResizing(false);
            saveWidth(stateKey, next);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", stop);
        window.addEventListener("pointercancel", stop);
    };

    const cls = [
        "ui-tab",
        collapsed && "ui-tab_collapsed",
        animating && "ui-tab_animating",
        resizing && "ui-tab_resizing",
    ]
        .filter(Boolean)
        .join(" ");

    const widthVar = dragged != null ? `${dragged}px` : width ? `${width}vw` : null;

    return (
        <aside
            ref={ref}
            className={cls}
            style={
                {
                    right: offset,
                    zIndex: 120 + layer,
                    ...(widthVar ? { "--ui-tab-w": widthVar } : null),
                } as TabStyle
            }
            onTransitionEnd={(e) => {
                if (e.propertyName === "width") setAnimating(false);
            }}
            onTransitionCancel={(e) => {
                if (e.propertyName === "width") setAnimating(false);
            }}
        >
            {!collapsed && (
                <div
                    className="ui-tab__grip"
                    onPointerDown={startResize}
                    onDoubleClick={() => {
                        setDragged(null);
                        saveWidth(stateKey, null);
                    }}
                    title="Drag to resize — double-click to reset"
                    role="separator"
                    aria-orientation="vertical"
                />
            )}
            <button
                type="button"
                className="ui-tab__strip"
                onClick={() => toggle(false)}
                title={`Expand ${accessibleTitle}`}
                aria-label={`Expand ${accessibleTitle}`}
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
                            aria-label={`Collapse ${accessibleTitle}`}
                        >
                            <ChevronRight width={16} height={16} />
                        </button>
                        <button
                            type="button"
                            className="ui-tab__icon-btn"
                            onClick={onClose}
                            title="Close"
                            aria-label={`Close ${accessibleTitle}`}
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
