import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWindowedRows } from "./useWindowedRows.js";

/**
 * The hook measures against `window.scrollY`, `window.innerHeight` and the
 * anchor's own top edge, none of which jsdom moves on its own — so each test
 * drives them by hand and fires the scroll event the hook listens for.
 */
const ROW_H = 40;

function anchorAt(top) {
    const el = document.createElement("div");
    el.getBoundingClientRect = () => ({ top, bottom: top, left: 0, right: 0, width: 0, height: 0 });
    return { current: el };
}

// jsdom's scrollY/innerHeight are read-only accessors, so redefine them
const setScrollY = (y) => Object.defineProperty(window, "scrollY", { value: y, configurable: true });

function scrollTo(y) {
    setScrollY(y);
    act(() => {
        window.dispatchEvent(new Event("scroll"));
        vi.runAllTimers();
    });
}

beforeEach(() => {
    vi.useFakeTimers();
    // rAF under fake timers so the coalesced measure runs when we advance time
    vi.stubGlobal("requestAnimationFrame", (cb) => setTimeout(() => cb(0), 0));
    vi.stubGlobal("cancelAnimationFrame", (id) => clearTimeout(id));
    setScrollY(0);
    Object.defineProperty(window, "innerHeight", { value: 400, configurable: true });
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe("useWindowedRows", () => {
    it("windows the top of the list at scroll 0 and pads for the rest", () => {
        const { result } = renderHook(() =>
            useWindowedRows({ count: 1000, rowHeight: ROW_H, anchorRef: anchorAt(0) }),
        );
        // 400px viewport / 40px rows = 10 visible, + 10 overscan below
        expect(result.current.start).toBe(0);
        expect(result.current.end).toBe(20);
        expect(result.current.padTop).toBe(0);
        expect(result.current.padBottom).toBe(980 * ROW_H);
    });

    it("moves the window and both spacers as the page scrolls", () => {
        const { result } = renderHook(() =>
            useWindowedRows({ count: 1000, rowHeight: ROW_H, anchorRef: anchorAt(0) }),
        );
        scrollTo(4000); // row 100 is at the top of the viewport

        expect(result.current.start).toBe(90);
        expect(result.current.end).toBe(120);
        expect(result.current.padTop).toBe(90 * ROW_H);
        expect(result.current.padBottom).toBe(880 * ROW_H);
    });

    it("clamps the window to the ends of a short list", () => {
        const { result } = renderHook(() =>
            useWindowedRows({ count: 5, rowHeight: ROW_H, anchorRef: anchorAt(0) }),
        );
        scrollTo(10_000);

        expect(result.current.start).toBe(0);
        expect(result.current.end).toBe(5);
        expect(result.current.padTop).toBe(0);
        expect(result.current.padBottom).toBe(0);
    });

    it("honours a custom overscan", () => {
        const { result } = renderHook(() =>
            useWindowedRows({
                count: 1000,
                rowHeight: ROW_H,
                anchorRef: anchorAt(0),
                overscan: 0,
            }),
        );
        scrollTo(4000);

        expect(result.current.start).toBe(100);
        expect(result.current.end).toBe(110);
    });

    it("accounts for an anchor that does not start at the top of the page", () => {
        const { result } = renderHook(() =>
            useWindowedRows({ count: 1000, rowHeight: ROW_H, anchorRef: anchorAt(200) }),
        );
        // rows begin 200px down, so scrolling 200px only reaches row 0
        scrollTo(200);

        expect(result.current.start).toBe(0);
        expect(result.current.end).toBe(20);
    });

    it("falls back to a top window when the list shrinks past the current range", () => {
        const anchor = anchorAt(0);
        const { result, rerender } = renderHook((props) => useWindowedRows(props), {
            initialProps: { count: 1000, rowHeight: ROW_H, anchorRef: anchor },
        });
        scrollTo(4000);
        expect(result.current.start).toBe(90);

        // a filter cuts the list to 3 rows while the window sits at row 90:
        // the render before the effect re-measures must still show rows
        rerender({ count: 3, rowHeight: ROW_H, anchorRef: anchor });
        expect(result.current.start).toBe(0);
        expect(result.current.end).toBe(3);
        expect(result.current.padTop).toBe(0);
        expect(result.current.padBottom).toBe(0);
    });

    it("renders an empty window for an empty list", () => {
        const { result } = renderHook(() =>
            useWindowedRows({ count: 0, rowHeight: ROW_H, anchorRef: anchorAt(0) }),
        );
        expect(result.current).toEqual({ start: 0, end: 0, padTop: 0, padBottom: 0 });
    });

    it("does nothing without an anchor element or a row height", () => {
        const { result: noAnchor } = renderHook(() =>
            useWindowedRows({ count: 100, rowHeight: ROW_H, anchorRef: { current: null } }),
        );
        scrollTo(4000);
        expect(noAnchor.current.end).toBe(60); // untouched initial window

        const { result: noHeight } = renderHook(() =>
            useWindowedRows({ count: 100, rowHeight: 0, anchorRef: anchorAt(0) }),
        );
        expect(noHeight.current).toEqual({ start: 0, end: 60, padTop: 0, padBottom: 0 });
    });

    it("coalesces a burst of scroll events into a single measure", () => {
        const { result } = renderHook(() =>
            useWindowedRows({ count: 1000, rowHeight: ROW_H, anchorRef: anchorAt(0) }),
        );
        act(() => {
            setScrollY(400);
            window.dispatchEvent(new Event("scroll"));
            setScrollY(800);
            window.dispatchEvent(new Event("scroll"));
            setScrollY(4000);
            window.dispatchEvent(new Event("resize"));
            vi.runAllTimers();
        });
        // one frame, one measure — against the latest scroll position
        expect(result.current.start).toBe(90);
    });

    it("stops measuring after unmount", () => {
        const { result, unmount } = renderHook(() =>
            useWindowedRows({ count: 1000, rowHeight: ROW_H, anchorRef: anchorAt(0) }),
        );
        act(() => {
            setScrollY(4000);
            window.dispatchEvent(new Event("scroll"));
        });
        unmount(); // a frame is still pending: the cleanup must cancel it
        act(() => {
            vi.runAllTimers();
        });
        expect(result.current.start).toBe(0);
    });
});
