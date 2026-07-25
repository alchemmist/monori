import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useWindowedRows } from "./useWindowedRows.js";

describe("useWindowedRows", () => {
    it("starts with a bounded top window and spacer for the remainder", () => {
        const anchorRef = { current: { getBoundingClientRect: () => ({ top: 1000 }) } };
        const { result } = renderHook(() => useWindowedRows({ count: 100, rowHeight: 20, anchorRef, overscan: 2 }));
        expect(result.current).toEqual({ start: 0, end: 0, padTop: 0, padBottom: 2000 });
    });

    it("remeasures on scroll and cleans up its listeners", () => {
        const anchorRef = { current: { getBoundingClientRect: () => ({ top: 0 }) } };
        const add = vi.spyOn(window, "addEventListener");
        const remove = vi.spyOn(window, "removeEventListener");
        vi.stubGlobal("requestAnimationFrame", (cb) => { cb(); return 1; });
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        const { result, unmount } = renderHook(() => useWindowedRows({ count: 10, rowHeight: 10, anchorRef }));
        act(() => window.dispatchEvent(new Event("scroll")));
        expect(result.current.end).toBe(10);
        expect(add).toHaveBeenCalledWith("scroll", expect.any(Function), { passive: true });
        unmount();
        expect(remove).toHaveBeenCalledWith("resize", expect.any(Function));
    });

    it("falls back to the top when a shrinking list leaves the old range behind", () => {
        const anchorRef = { current: null };
        const { result } = renderHook(() => useWindowedRows({ count: 3, rowHeight: 10, anchorRef }));
        expect(result.current).toEqual({ start: 0, end: 3, padTop: 0, padBottom: 0 });
    });
});
