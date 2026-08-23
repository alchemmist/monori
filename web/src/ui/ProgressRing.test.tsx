import { afterEach, describe, expect, it } from "vitest";
import ProgressRing from "./ProgressRing.jsx";
import { render, renderUI, screen } from "../test/render.jsx";

const realMatchMedia = window.matchMedia.bind(window);

/** Make `(prefers-reduced-motion: reduce)` match, leaving other queries alone. */
function reduceMotion() {
    window.matchMedia = (query) =>
        Object.assign(realMatchMedia(query), {
            matches: query.includes("prefers-reduced-motion"),
        });
}

afterEach(() => {
    Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: realMatchMedia,
    });
});

describe("ProgressRing", () => {
    it("draws the ring and labels it for assistive tech", () => {
        const { container } = renderUI(<ProgressRing value={0.42} label="Importing" />);
        const ring = screen.getByRole("status", { name: "Importing" });
        expect(ring).toHaveTextContent("42%");
        expect(ring).toHaveAttribute("title", "Importing");
        expect(container.querySelector<HTMLElement>("svg")!).toHaveAttribute("aria-hidden", "true");
    });

    it("sweeps the arc in proportion to the value", () => {
        const { container } = renderUI(<ProgressRing value={0.25} label="x" />);
        const arc = container.querySelector<HTMLElement>(".progress-ring__value")!;
        const total = Number(arc.getAttribute("stroke-dasharray"));
        expect(Number(arc.getAttribute("stroke-dashoffset"))).toBeCloseTo(total * 0.75);
    });

    it("leaves the arc fully hidden at zero and fully drawn at one", () => {
        const { container, unmount } = renderUI(<ProgressRing value={0} label="x" />);
        const empty = container.querySelector<HTMLElement>(".progress-ring__value")!;
        expect(Number(empty.getAttribute("stroke-dashoffset"))).toBeCloseTo(
            Number(empty.getAttribute("stroke-dasharray")),
        );
        unmount();

        const full = renderUI(<ProgressRing value={1} label="x" />);
        expect(
            Number(
                full.container
                    .querySelector<HTMLElement>(".progress-ring__value")!
                    .getAttribute("stroke-dashoffset"),
            ),
        ).toBeCloseTo(0);
    });

    it("clamps values outside 0..1 instead of overdrawing", () => {
        const { unmount } = renderUI(<ProgressRing value={-3} label="under" />);
        expect(screen.getByRole("status")).toHaveTextContent("0%");
        unmount();
        renderUI(<ProgressRing value={7} label="over" />);
        expect(screen.getByRole("status")).toHaveTextContent("100%");
    });

    it("shows the bare percentage and no svg under reduced motion", () => {
        reduceMotion();
        const { container } = renderUI(<ProgressRing value={0.6} label="Importing" />);
        expect(screen.getByRole("status", { name: "Importing" })).toHaveTextContent("60%");
        expect(container.querySelector<HTMLElement>("svg")!).toBeNull();
    });

    // an environment that cannot answer the query has not asked for reduced
    // motion — assuming it did would strip the ring from every such browser.
    // These render without the Mantine provider, which needs a real matchMedia.
    it.each([
        ["answers nothing", () => undefined],
        ["answers without a matches field", () => ({})],
        ["is missing entirely", undefined],
    ])("still draws the ring when matchMedia %s", (_label, stub) => {
        Object.defineProperty(window, "matchMedia", { configurable: true, value: stub });
        const { container } = render(<ProgressRing value={0.5} label="x" />);
        expect(container.querySelector<HTMLElement>(".progress-ring__value")!).toBeInTheDocument();
        expect(container.querySelector<HTMLElement>("svg")!).toBeInTheDocument();
    });
});
