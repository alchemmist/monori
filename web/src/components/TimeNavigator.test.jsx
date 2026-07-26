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
        Object.defineProperty(HTMLElement.prototype, "clientWidth", {
            configurable: true,
            get: () => 1200,
        });
        SVGElement.prototype.setPointerCapture = () => {};
    });
    it("draws the history, year marks and selected window", () => {
        renderUI(<TimeNavigator items={items} range={[1, 3]} onChange={vi.fn()} />);
        expect(document.querySelector(".timenav__area")).toHaveAttribute(
            "d",
            "M 120 56 L 120 39.5 C 160 37.583333333333336, 280 31.833333333333332, 360 28 C 440 24.166666666666668, 520 15.733333333333334, 600 16.5 C 680 17.266666666666666, 760 34.51666666666666, 840 32.599999999999994 C 920 30.683333333333326, 1040 9.599999999999998, 1080 5 L 1080 56 Z",
        );
        expect(screen.getByText("2026")).toBeInTheDocument();
        const windowRect = document.querySelector(".timenav__window");
        expect(windowRect).toHaveAttribute("x", "240");
        expect(windowRect).toHaveAttribute("width", "720");
        const [before, after] = document.querySelectorAll(".timenav__dim");
        expect(before).toHaveAttribute("width", "240");
        expect(after).toHaveAttribute("width", "240");
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
        fireEvent.pointerDown(document.querySelectorAll(".timenav__handle")[0], {
            pointerId: 2,
            clientX: 300,
        });
        fireEvent.pointerMove(svg, { pointerId: 2, clientX: 700 });
        expect(onChange).toHaveBeenLastCalledWith([1, 3]);
    });

    it("centres the window when clicking the overview track", () => {
        const onChange = vi.fn();
        renderUI(<TimeNavigator items={items} range={[0, 2]} onChange={onChange} />);
        fireEvent.pointerDown(document.querySelector("svg"), { pointerId: 1, clientX: 1100 });
        expect(onChange).toHaveBeenCalledWith([2, 4]);
    });

    it("clamps a moved window to both ends while preserving its inclusive span", () => {
        const onChange = vi.fn();
        renderUI(<TimeNavigator items={items} range={[1, 3]} onChange={onChange} />);
        const svg = document.querySelector("svg");
        const windowRect = document.querySelector(".timenav__window");

        fireEvent.pointerDown(windowRect, { pointerId: 1, clientX: 500 });
        fireEvent.pointerMove(svg, { pointerId: 1, clientX: -500 });
        expect(onChange).toHaveBeenLastCalledWith([0, 2]);
        fireEvent.pointerUp(svg, { pointerId: 1 });

        fireEvent.pointerDown(windowRect, { pointerId: 2, clientX: 500 });
        fireEvent.pointerMove(svg, { pointerId: 2, clientX: 1500 });
        expect(onChange).toHaveBeenLastCalledWith([2, 4]);
    });

    it("does not let either resize handle shrink the window below three months", () => {
        const onChange = vi.fn();
        renderUI(<TimeNavigator items={items} range={[1, 3]} onChange={onChange} />);
        const svg = document.querySelector("svg");
        const [left, right] = document.querySelectorAll(".timenav__handle");

        fireEvent.pointerDown(left, { pointerId: 1, clientX: 100 });
        fireEvent.pointerMove(svg, { pointerId: 1, clientX: 1000 });
        expect(onChange).toHaveBeenLastCalledWith([1, 3]);
        fireEvent.pointerUp(svg, { pointerId: 1 });

        fireEvent.pointerDown(right, { pointerId: 2, clientX: 800 });
        fireEvent.pointerMove(svg, { pointerId: 2, clientX: -100 });
        expect(onChange).toHaveBeenLastCalledWith([1, 3]);
    });

    it("resizes each edge by whole months and keeps the opposite edge fixed", () => {
        const onChange = vi.fn();
        renderUI(<TimeNavigator items={items} range={[1, 4]} onChange={onChange} />);
        const svg = document.querySelector("svg");
        const [left, right] = document.querySelectorAll(".timenav__handle");

        fireEvent.pointerDown(left, { pointerId: 1, clientX: 300 });
        fireEvent.pointerMove(svg, { pointerId: 1, clientX: 540 });
        expect(onChange).toHaveBeenLastCalledWith([2, 4]);
        fireEvent.pointerUp(svg, { pointerId: 1 });

        fireEvent.pointerDown(right, { pointerId: 2, clientX: 900 });
        fireEvent.pointerMove(svg, { pointerId: 2, clientX: 660 });
        expect(onChange).toHaveBeenLastCalledWith([1, 3]);
    });

    it("does not render an SVG for an empty history", () => {
        renderUI(<TimeNavigator items={[]} range={[0, 0]} onChange={vi.fn()} />);
        expect(document.querySelector("svg")).not.toBeInTheDocument();
    });
});
