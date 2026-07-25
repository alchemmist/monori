import { describe, expect, it, vi, beforeEach } from "vitest";
import EnvelopeHero from "./EnvelopeHero.jsx";
import { renderUI } from "../test/render.jsx";

describe("EnvelopeHero", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("is decorative: a canvas over a stage hidden from the accessibility tree", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const stage = container.querySelector(".env-hero");
        expect(stage).toHaveAttribute("aria-hidden", "true");
        expect(stage.querySelector("canvas")).toHaveClass("env-hero__canvas");
    });

    it("lays out the four envelopes, each with its amount above its name", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const envs = [...container.querySelectorAll(".env-hero__row .env-hero__env")];
        expect(
            envs.map((env) => [
                env.querySelector(".env-hero__pocket .env-hero__amt.num").textContent,
                env.querySelector(".env-hero__name").textContent,
            ]),
        ).toEqual([
            ["12 000", "Groceries"],
            ["4 000", "Transport"],
            ["6 000", "Eating out"],
            ["20 000", "Savings"],
        ]);
    });

    it("marks only the overspent envelope as hot", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const hot = [...container.querySelectorAll(".env-hero__env")].filter((el) =>
            el.classList.contains("is-hot"),
        );
        expect(hot).toHaveLength(1);
        expect(hot[0].querySelector(".env-hero__name")).toHaveTextContent("Eating out");
    });

    it("does not start canvas work when reduced motion is requested", () => {
        const observe = vi.fn();
        vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true });
        vi.stubGlobal(
            "IntersectionObserver",
            vi.fn(() => ({ observe, disconnect: vi.fn() })),
        );
        const context = { clearRect: vi.fn() };
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);

        renderUI(<EnvelopeHero />);
        expect(observe).not.toHaveBeenCalled();
        expect(context.clearRect).not.toHaveBeenCalled();
        vi.unstubAllGlobals();
    });

    it("sizes, animates, pauses and cleans up when visibility changes", () => {
        let onIntersection;
        const observe = vi.fn();
        const disconnect = vi.fn();
        const cancel = vi.fn();
        const frame = vi.fn(() => 42);
        const context = {
            clearRect: vi.fn(),
            beginPath: vi.fn(),
            arc: vi.fn(),
            fill: vi.fn(),
            globalAlpha: 1,
        };
        vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false });
        vi.stubGlobal(
            "IntersectionObserver",
            class {
                constructor(callback) {
                    onIntersection = callback;
                }
                observe = observe;
                disconnect = disconnect;
            },
        );
        vi.stubGlobal("requestAnimationFrame", frame);
        vi.stubGlobal("cancelAnimationFrame", cancel);
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);
        const { container, unmount } = renderUI(<EnvelopeHero />);
        const stage = container.querySelector(".env-hero");
        Object.defineProperty(stage, "clientWidth", { configurable: true, value: 300 });
        Object.defineProperty(stage, "clientHeight", { configurable: true, value: 120 });

        onIntersection([{ isIntersecting: true }]);
        const canvas = container.querySelector("canvas");
        expect(observe).toHaveBeenCalledWith(stage);
        expect(canvas).toHaveProperty("width", 300);
        expect(canvas).toHaveProperty("height", 120);
        expect(frame).toHaveBeenCalled();

        onIntersection([{ isIntersecting: false }]);
        expect(cancel).toHaveBeenCalledWith(42);
        unmount();
        expect(disconnect).toHaveBeenCalled();
        expect(cancel).toHaveBeenCalled();
        vi.unstubAllGlobals();
    });

    it("draws spawned coins on animation frames", () => {
        let onIntersection;
        let animation;
        const context = {
            clearRect: vi.fn(),
            beginPath: vi.fn(),
            arc: vi.fn(),
            fill: vi.fn(),
            globalAlpha: 1,
        };
        vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false });
        vi.spyOn(window, "getComputedStyle").mockReturnValue({
            getPropertyValue: (name) => (name === "--m-text" ? "#111" : "#f00"),
        });
        vi.stubGlobal(
            "IntersectionObserver",
            class {
                constructor(callback) {
                    onIntersection = callback;
                }
                observe() {}
                disconnect() {}
            },
        );
        vi.stubGlobal(
            "requestAnimationFrame",
            vi.fn((callback) => {
                animation = callback;
                return 7;
            }),
        );
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);
        vi.spyOn(Math, "random").mockReturnValue(0.5);
        const { container } = renderUI(<EnvelopeHero />);
        const stage = container.querySelector(".env-hero");
        Object.defineProperty(stage, "clientWidth", { configurable: true, value: 300 });
        Object.defineProperty(stage, "clientHeight", { configurable: true, value: 200 });
        stage.getBoundingClientRect = () => ({ left: 0 });
        stage.querySelectorAll(".env-hero__pocket").forEach((pocket, index) => {
            pocket.getBoundingClientRect = () => ({ left: index * 50, width: 40 });
        });

        onIntersection([{ isIntersecting: true }]);
        animation(301);
        expect(context.clearRect).toHaveBeenCalled();
        expect(context.arc).toHaveBeenCalled();
        expect(context.fill).toHaveBeenCalled();
        expect(context.fillStyle).toBe("#111");
        // Advance the same coin through the floor: expired particles are removed
        // instead of being drawn indefinitely.
        for (let timestamp = 602; timestamp < 30000; timestamp += 301) animation(timestamp);
        vi.unstubAllGlobals();
    });
});
