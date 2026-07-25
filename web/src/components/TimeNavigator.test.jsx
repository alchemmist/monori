import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderUI, screen } from "../test/render.jsx";
import TimeNavigator from "./TimeNavigator.jsx";

const items = [
    { key: "2025-11", value: 5 },
    { key: "2025-12", value: 10 },
    { key: "2026-01", value: 15 },
    { key: "2026-02", value: 8 },
    { key: "2026-03", value: 20 },
];

describe("TimeNavigator", () => {
    beforeEach(() => {
        Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 1200 });
        SVGElement.prototype.setPointerCapture = () => {};
    });
    it("draws the history, year marks and selected window", () => {
        renderUI(<TimeNavigator items={items} range={[1, 3]} onChange={vi.fn()} />);
        expect(document.querySelector(".timenav__area")).toHaveAttribute("d", expect.stringContaining("C"));
        expect(screen.getByText("2026")).toBeInTheDocument();
        expect(document.querySelector(".timenav__window")).toHaveAttribute("width", "720");
    });

    it("moves and resizes the range through pointer gestures", () => {
        const onChange = vi.fn();
        renderUI(<TimeNavigator items={items} range={[1, 3]} onChange={onChange} />);
        const svg = document.querySelector("svg");
        const windowRect = document.querySelector(".timenav__window");
        fireEvent.pointerDown(windowRect, { pointerId: 1, clientX: 100 });
        fireEvent.pointerMove(svg, { pointerId: 1, clientX: 350 });
        expect(onChange).toHaveBeenLastCalledWith([2, 4]);
        fireEvent.pointerUp(svg, { pointerId: 1 });
        fireEvent.pointerDown(document.querySelectorAll(".timenav__handle")[0], { pointerId: 2, clientX: 300 });
        fireEvent.pointerMove(svg, { pointerId: 2, clientX: 700 });
        expect(onChange).toHaveBeenLastCalledWith([1, 3]);
    });

    it("centres the window when clicking the overview track", () => {
        const onChange = vi.fn();
        renderUI(<TimeNavigator items={items} range={[0, 2]} onChange={onChange} />);
        fireEvent.pointerDown(document.querySelector("svg"), { pointerId: 1, clientX: 1100 });
        expect(onChange).toHaveBeenCalledWith([2, 4]);
    });

    it("does not render an SVG for an empty history", () => {
        renderUI(<TimeNavigator items={[]} range={[0, 0]} onChange={vi.fn()} />);
        expect(document.querySelector("svg")).not.toBeInTheDocument();
    });
});
