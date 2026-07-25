import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useWindowedRows } from "./useWindowedRows.js";

/** An anchor whose top edge sits `top` px below the current scroll position. */
const anchorAt = (top) => ({ current: { getBoundingClientRect: () => ({ top }) } });

/** Drive window.scrollY/innerHeight, which the hook measures against. */
function setViewport({ scrollY = 0, innerHeight = 800 } = {}) {
    Object.defineProperty(window, "scrollY", { configurable: true, value: scrollY });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: innerHeight });
}

const original = { scrollY: window.scrollY, innerHeight: window.innerHeight };

beforeEach(() => {
    setViewport();
    // the hook coalesces through rAF; run the callback inline so a dispatched
    // scroll event is measured within the same act()
    vi.stubGlobal("requestAnimationFrame", (cb) => {
        cb();
        return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
});

afterEach(() => {
    setViewport(original);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe("useWindowedRows", () => {
    it("renders only the rows the viewport can reach, padding out the rest", () => {
        setViewport({ scrollY: 0, innerHeight: 100 });
        // anchor 1000px down: row 0 is far below the fold, so nothing renders yet
        // and the whole list is bottom spacer
        const { result } = renderHook(() =>
            useWindowedRows({ count: 100, rowHeight: 20, anchorRef: anchorAt(1000), overscan: 2 }),
        );
        expect(result.current).toEqual({ start: 0, end: 0, padTop: 0, padBottom: 2000 });
    });

    it("windows around the scroll position, with spacers that keep the list the same height", () => {
        // anchor at the top of the document, scrolled 1000px down into it
        setViewport({ scrollY: 1000, innerHeight: 200 });
        const { result } = renderHook(() =>
            useWindowedRows({ count: 500, rowHeight: 20, anchorRef: anchorAt(-1000), overscan: 3 }),
        );
        // first = floor(1000/20) = 50, visible = ceil(200/20) = 10
        expect(result.current.start).toBe(47);
        expect(result.current.end).toBe(63);
        expect(result.current.start).toBeGreaterThan(0);
        expect(result.current.padTop).toBe(47 * 20);
        expect(result.current.padBottom).toBe((500 - 63) * 20);
        // the spacers plus the rendered rows always add up to the full list
        expect(
            result.current.padTop +
                (result.current.end - result.current.start) * 20 +
                result.current.padBottom,
        ).toBe(500 * 20);
    });

    it("pads by whole rows already scrolled past, never rounding a partial row away", () => {
        // 1010px of scroll is row 50 plus half of row 51 — the first rendered row
        // must be 50, so the spacer never overshoots and jump the list upward
        setViewport({ scrollY: 1010, innerHeight: 200 });
        const { result } = renderHook(() =>
            useWindowedRows({ count: 500, rowHeight: 20, anchorRef: anchorAt(-1010), overscan: 0 }),
        );
        expect(result.current.start).toBe(50);
        expect(result.current.padTop).toBe(1000);
    });

    it("keeps a default overscan of rows rendered beyond the viewport on each side", () => {
        setViewport({ scrollY: 1000, innerHeight: 200 });
        const { result } = renderHook(() =>
            useWindowedRows({ count: 500, rowHeight: 20, anchorRef: anchorAt(-1000) }),
        );
        // default overscan is 10: 50-10 above, 50+10(visible)+10 below
        expect(result.current.start).toBe(40);
        expect(result.current.end).toBe(70);
    });

    it("renders the whole visible run, not just the overscan", () => {
        setViewport({ scrollY: 0, innerHeight: 400 });
        const { result } = renderHook(() =>
            useWindowedRows({ count: 500, rowHeight: 20, anchorRef: anchorAt(0), overscan: 2 }),
        );
        // visible = ceil(400/20) = 20, so end must clear the fold: 0 + 20 + 2
        expect(result.current.start).toBe(0);
        expect(result.current.end).toBe(22);
    });

    it("remeasures on scroll and tears down every listener it added", () => {
        const add = vi.spyOn(window, "addEventListener");
        const remove = vi.spyOn(window, "removeEventListener");
        const cancel = vi.fn();
        // hand back a pending handle so unmount has something to cancel
        vi.stubGlobal("requestAnimationFrame", () => 42);
        vi.stubGlobal("cancelAnimationFrame", cancel);
        setViewport({ scrollY: 0, innerHeight: 100 });

        const { result, unmount } = renderHook(() =>
            useWindowedRows({ count: 500, rowHeight: 10, anchorRef: anchorAt(0), overscan: 0 }),
        );
        expect(result.current.end).toBe(10);

        expect(add).toHaveBeenCalledWith("scroll", expect.any(Function), { passive: true });
        expect(add).toHaveBeenCalledWith("resize", expect.any(Function));
        const onScroll = add.mock.calls.find((c) => c[0] === "scroll")[1];

        // a queued frame that never ran must be cancelled, not left dangling
        act(() => window.dispatchEvent(new Event("scroll")));
        unmount();
        expect(remove).toHaveBeenCalledWith("scroll", onScroll);
        expect(remove).toHaveBeenCalledWith("resize", onScroll);
        expect(cancel).toHaveBeenCalledWith(42);
    });

    it("re-windows when a scroll actually moves the viewport", () => {
        setViewport({ scrollY: 0, innerHeight: 200 });
        const anchorRef = anchorAt(0);
        const { result } = renderHook(() =>
            useWindowedRows({ count: 500, rowHeight: 20, anchorRef, overscan: 1 }),
        );
        expect(result.current.start).toBe(0);

        // scrollY moves and the anchor scrolls with the page, so its viewport-
        // relative top goes negative by the same amount
        anchorRef.current.getBoundingClientRect = () => ({ top: -2000 });
        setViewport({ scrollY: 2000, innerHeight: 200 });
        act(() => window.dispatchEvent(new Event("scroll")));

        expect(result.current.start).toBe(99);
        expect(result.current.padTop).toBe(99 * 20);
    });

    it("falls back to a top window when a shrinking list leaves the old range behind", () => {
        setViewport({ scrollY: 4000, innerHeight: 200 });
        const anchorRef = anchorAt(-4000);
        const { result, rerender } = renderHook((props) => useWindowedRows(props), {
            initialProps: { count: 500, rowHeight: 10, anchorRef, overscan: 0 },
        });
        // scrolled deep: the window sits at row 400, far past the shrunk list
        expect(result.current.start).toBe(400);

        // a filter cuts the list down to 3 rows while the stale range still says 400
        rerender({ count: 3, rowHeight: 10, anchorRef: { current: null }, overscan: 0 });
        expect(result.current).toEqual({ start: 0, end: 3, padTop: 0, padBottom: 0 });
    });

    it("caps the fallback window instead of painting the entire long list", () => {
        setViewport({ scrollY: 20000, innerHeight: 200 });
        const anchorRef = anchorAt(-20000);
        const { result, rerender } = renderHook((props) => useWindowedRows(props), {
            initialProps: { count: 5000, rowHeight: 10, anchorRef, overscan: 0 },
        });
        expect(result.current.start).toBe(2000);

        rerender({ count: 900, rowHeight: 10, anchorRef: { current: null }, overscan: 0 });
        expect(result.current.start).toBe(0);
        expect(result.current.end).toBe(60);
        expect(result.current.padBottom).toBe((900 - 60) * 10);
    });

    it("does not treat a range that ends exactly at the last row as fallen past the end", () => {
        setViewport({ scrollY: 50, innerHeight: 20 });
        const anchorRef = anchorAt(-50);
        const { result, rerender } = renderHook((props) => useWindowedRows(props), {
            initialProps: { count: 100, rowHeight: 10, anchorRef, overscan: 0 },
        });
        expect(result.current.start).toBe(5);

        // shrink to exactly start+1 rows: row 5 is still the last real row, so the
        // window is valid and must be kept rather than reset to the top
        rerender({ count: 6, rowHeight: 10, anchorRef: { current: null }, overscan: 0 });
        expect(result.current.start).toBe(5);
        expect(result.current.end).toBe(6);

        // one row fewer and the window really is past the end
        rerender({ count: 5, rowHeight: 10, anchorRef: { current: null }, overscan: 0 });
        expect(result.current.start).toBe(0);
        expect(result.current.end).toBe(5);
    });

    it("stays idle until it has both an anchor and a row height", () => {
        const add = vi.spyOn(window, "addEventListener");
        renderHook(() => useWindowedRows({ count: 10, rowHeight: 0, anchorRef: anchorAt(0) }));
        renderHook(() =>
            useWindowedRows({ count: 10, rowHeight: 10, anchorRef: { current: null } }),
        );
        expect(add).not.toHaveBeenCalledWith("scroll", expect.any(Function), { passive: true });
    });

    // before the anchor exists there is nothing to measure against, so the very
    // first paint has to show a usable top window — an empty one would render a
    // blank list until the ref attaches and the effect runs
    it("paints a bounded top window on the first render, before any measurement", () => {
        const { result } = renderHook(() =>
            useWindowedRows({ count: 500, rowHeight: 10, anchorRef: { current: null } }),
        );
        expect(result.current).toEqual({ start: 0, end: 60, padTop: 0, padBottom: 4400 });
    });

    it("shows the whole list on the first render when it is shorter than the window", () => {
        const { result } = renderHook(() =>
            useWindowedRows({ count: 12, rowHeight: 10, anchorRef: { current: null } }),
        );
        expect(result.current).toEqual({ start: 0, end: 12, padTop: 0, padBottom: 0 });
    });
});
