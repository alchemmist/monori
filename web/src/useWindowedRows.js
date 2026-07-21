import { useEffect, useState } from "react";

/**
 * Windowed (virtualized) rendering over the page's own (window) scroll.
 *
 * Given a fixed row height and an anchor element that marks where row 0 begins
 * (its top edge must be stable regardless of how many rows are windowed — the
 * `<tbody>` works, since the leading spacer lives inside it), returns the slice
 * `[start, end)` of rows to render plus the spacer heights that stand in for the
 * off-screen rows above and below. DOM size stays constant no matter how long
 * the list is.
 */
export function useWindowedRows({ count, rowHeight, anchorRef, overscan = 10 }) {
    const [range, setRange] = useState({ start: 0, end: Math.min(count, 60) });

    useEffect(() => {
        const anchor = anchorRef.current;
        if (!anchor || !rowHeight) return;

        let raf = 0;
        const measure = () => {
            raf = 0;
            const rowsTop = anchor.getBoundingClientRect().top + window.scrollY;
            const first = Math.floor((window.scrollY - rowsTop) / rowHeight);
            const visible = Math.ceil(window.innerHeight / rowHeight);
            const start = Math.max(0, Math.min(count, first - overscan));
            const end = Math.max(0, Math.min(count, first + visible + overscan));
            setRange((r) => (r.start === start && r.end === end ? r : { start, end }));
        };
        const onScroll = () => {
            // coalesce bursts of scroll/resize into one measure per frame
            if (!raf) raf = requestAnimationFrame(measure);
        };

        measure();
        window.addEventListener("scroll", onScroll, { passive: true });
        window.addEventListener("resize", onScroll);
        return () => {
            window.removeEventListener("scroll", onScroll);
            window.removeEventListener("resize", onScroll);
            if (raf) cancelAnimationFrame(raf);
        };
    }, [count, rowHeight, anchorRef, overscan]);

    // when the list shrinks below the previous window (a filter applied while
    // scrolled deep), the old range can sit entirely past the new end — clamping
    // alone would give start===end===count and paint a blank list for one frame.
    // Fall back to a top window until the scroll effect re-measures next frame.
    const fellPastEnd = count > 0 && range.start >= count;
    const start = fellPastEnd ? 0 : Math.min(range.start, count);
    const end = fellPastEnd ? Math.min(count, 60) : Math.min(range.end, count);
    return { start, end, padTop: start * rowHeight, padBottom: (count - end) * rowHeight };
}
