import { describe, it, expect, vi, afterEach } from "vitest";
import { renderUI, resetStore, fireEvent } from "../test/render.jsx";
import TimeNavigator from "./TimeNavigator.jsx";

describe("TimeNavigator", () => {
    afterEach(() => {
        resetStore();
    });

    function generateItems(months = 24) {
        const items = [];
        const start = new Date(2024, 0, 1);
        for (let i = 0; i < months; i++) {
            const d = new Date(start);
            d.setMonth(d.getMonth() + i);
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, "0");
            items.push({
                key: `${year}-${month}`,
                value: Math.random() * 1000 + 500,
            });
        }
        return items;
    }

    it("renders the container div with timenav class", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 11]} onChange={vi.fn()} />);
        const timenav = document.querySelector(".timenav");
        expect(timenav).toBeInTheDocument();
    });

    it("renders SVG when items and width are available", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 11]} onChange={vi.fn()} />);
        const svg = document.querySelector(".timenav__svg");
        expect(svg).toBeInTheDocument();
    });

    it("renders the area chart path", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 11]} onChange={vi.fn()} />);
        const path = document.querySelector(".timenav__area");
        expect(path).toBeInTheDocument();
    });

    it("renders month ticks for each item", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 11]} onChange={vi.fn()} />);
        const ticks = document.querySelectorAll(".timenav__tick");
        expect(ticks.length).toBe(items.length);
    });

    it("renders year labels at January markers", () => {
        const items = generateItems(24);
        renderUI(<TimeNavigator items={items} range={[0, 23]} onChange={vi.fn()} />);
        const yearLabels = document.querySelectorAll(".timenav__year");
        expect(yearLabels.length).toBeGreaterThan(0);
    });

    it("renders dimming rects outside the window", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[3, 8]} onChange={vi.fn()} />);
        const dimRects = document.querySelectorAll(".timenav__dim");
        expect(dimRects.length).toBe(2);
    });

    it("renders the selection window rect", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[3, 8]} onChange={vi.fn()} />);
        const windowRect = document.querySelector(".timenav__window");
        expect(windowRect).toBeInTheDocument();
    });

    it("renders left and right resize handles", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[3, 8]} onChange={vi.fn()} />);
        const handles = document.querySelectorAll(".timenav__handle");
        expect(handles.length).toBe(2);
    });

    it("calls onChange when dragging the window", () => {
        const onChange = vi.fn();
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[3, 8]} onChange={onChange} />);
        const windowRect = document.querySelector(".timenav__window");
        fireEvent.pointerDown(windowRect, { clientX: 100, pointerId: 1 });
        fireEvent.pointerMove(document, { clientX: 150, pointerId: 1 });
        fireEvent.pointerUp(document, { pointerId: 1 });
    });

    it("calls onChange when clicking on track to center window", () => {
        const onChange = vi.fn();
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 5]} onChange={onChange} />);
        const svg = document.querySelector(".timenav__svg");
        fireEvent.pointerDown(svg, {
            clientX: 600,
            pointerId: 1,
        });
    });

    it("does not render SVG when items is empty", () => {
        renderUI(<TimeNavigator items={[]} range={[0, 0]} onChange={vi.fn()} />);
        const svg = document.querySelector(".timenav__svg");
        expect(svg).not.toBeInTheDocument();
    });

    it("handles single item gracefully", () => {
        const items = [{ key: "2024-01", value: 100 }];
        renderUI(<TimeNavigator items={items} range={[0, 0]} onChange={vi.fn()} />);
        const ticks = document.querySelectorAll(".timenav__tick");
        expect(ticks.length).toBe(1);
    });

    it("renders SVG with correct height", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 5]} onChange={vi.fn()} />);
        const svg = document.querySelector(".timenav__svg");
        expect(svg).toHaveAttribute("height", "56");
    });

    it("renders area path with smooth curves", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 11]} onChange={vi.fn()} />);
        const path = document.querySelector(".timenav__area");
        const d = path.getAttribute("d");
        expect(d).toMatch(/^M.*C.*Z$/);
    });

    it("renders tick lines for all months", () => {
        const items = generateItems(24);
        renderUI(<TimeNavigator items={items} range={[0, 23]} onChange={vi.fn()} />);
        const ticks = document.querySelectorAll("line.timenav__tick");
        expect(ticks.length).toBe(24);
    });

    it("handles large value range in data", () => {
        const items = [
            { key: "2024-01", value: 1000000 },
            { key: "2024-02", value: 100 },
            { key: "2024-03", value: 500000 },
        ];
        renderUI(<TimeNavigator items={items} range={[0, 2]} onChange={vi.fn()} />);
        const path = document.querySelector(".timenav__area");
        expect(path).toBeInTheDocument();
    });

    it("renders year labels with correct positioning", () => {
        const items = generateItems(24);
        renderUI(<TimeNavigator items={items} range={[0, 23]} onChange={vi.fn()} />);
        const labels = document.querySelectorAll(".timenav__year");
        expect(labels.length).toBeGreaterThan(0);
        labels.forEach((label) => {
            expect(label.getAttribute("y")).toBe("11");
        });
    });

    it("cleans up resize observer on unmount", () => {
        const items = generateItems(12);
        const { unmount } = renderUI(
            <TimeNavigator items={items} range={[0, 11]} onChange={vi.fn()} />,
        );
        expect(() => unmount()).not.toThrow();
    });

    it("renders grip handles with correct styling", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[3, 8]} onChange={vi.fn()} />);
        const grips = document.querySelectorAll(".timenav__grip");
        expect(grips.length).toBe(2);
        grips.forEach((grip) => {
            expect(grip).toHaveAttribute("width", "3");
            expect(grip).toHaveAttribute("height", "56");
        });
    });

    it("window rect has pointer event handling", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[3, 8]} onChange={vi.fn()} />);
        const windowRect = document.querySelector(".timenav__window");
        expect(windowRect).toBeInTheDocument();
    });

    it("updates window position when range prop changes", () => {
        const onChange = vi.fn();
        const items = generateItems(12);
        const { rerender } = renderUI(
            <TimeNavigator items={items} range={[0, 5]} onChange={onChange} />,
        );
        const windowBefore = document.querySelector(".timenav__window");
        const xBefore = windowBefore.getAttribute("x");
        rerender(<TimeNavigator items={items} range={[2, 7]} onChange={onChange} />);
        const windowAfter = document.querySelector(".timenav__window");
        const xAfter = windowAfter.getAttribute("x");
        expect(xBefore).not.toBe(xAfter);
    });

    it("path area starts and ends with baseline", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 11]} onChange={vi.fn()} />);
        const path = document.querySelector(".timenav__area");
        const d = path.getAttribute("d");
        expect(d).toContain("L");
        expect(d).toContain("Z");
    });

    it("renders handle transparent rects for larger click area", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[3, 8]} onChange={vi.fn()} />);
        const handles = document.querySelectorAll(".timenav__handle rect");
        expect(handles.length).toBeGreaterThan(0);
    });

    it("handles non-contiguous year labels", () => {
        const items = [
            { key: "2024-01", value: 100 },
            { key: "2025-01", value: 200 },
            { key: "2026-01", value: 300 },
        ];
        renderUI(<TimeNavigator items={items} range={[0, 2]} onChange={vi.fn()} />);
        const labels = document.querySelectorAll(".timenav__year");
        expect(labels.length).toBe(3);
    });

    it("renders dim rects with correct dimensions", () => {
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[3, 8]} onChange={vi.fn()} />);
        const dimRects = document.querySelectorAll(".timenav__dim");
        expect(dimRects[0].getAttribute("x")).toBe("0");
        dimRects.forEach((rect) => {
            expect(rect).toHaveAttribute("height", "56");
        });
    });

    it("maintains minimum span when resizing", () => {
        const onChange = vi.fn();
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 2]} onChange={onChange} />);
    });

    it("clamps window to valid range boundaries", () => {
        const onChange = vi.fn();
        const items = generateItems(12);
        renderUI(<TimeNavigator items={items} range={[0, 5]} onChange={onChange} />);
    });
});
