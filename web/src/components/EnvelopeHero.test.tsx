import { describe, expect, it, vi, beforeEach } from "vitest";
import EnvelopeHero from "./EnvelopeHero.jsx";
import { renderUI } from "../test/render.jsx";

describe("EnvelopeHero", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("is decorative: a canvas over a stage hidden from the accessibility tree", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const stage = container.querySelector<HTMLElement>(".env-hero")!;
        expect(stage).toHaveAttribute("aria-hidden", "true");
        expect(stage.querySelector<HTMLElement>("canvas")!).toHaveClass("env-hero__canvas");
    });

    it("lays out the four envelopes, each with its amount above its name", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const envs = [...container.querySelectorAll<HTMLElement>(".env-hero__row .env-hero__env")];
        expect(
            envs.map((env) => [
                env.querySelector<HTMLElement>(".env-hero__pocket .env-hero__amt.num")!.textContent,
                env.querySelector<HTMLElement>(".env-hero__name")!.textContent,
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
        const hot = [...container.querySelectorAll<HTMLElement>(".env-hero__env")].filter((el) =>
            el.classList.contains("is-hot"),
        );
        expect(hot).toHaveLength(1);
        expect(hot[0]!.querySelector<HTMLElement>(".env-hero__name")!).toHaveTextContent(
            "Eating out",
        );
    });

    it("does not start canvas work when reduced motion is requested", () => {
        const observe = vi.fn();
        vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true } as MediaQueryList);
        vi.stubGlobal(
            "IntersectionObserver",
            vi.fn(() => ({ observe, disconnect: vi.fn() })),
        );
        const context = { clearRect: vi.fn() };
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
            context as unknown as CanvasRenderingContext2D,
        );

        renderUI(<EnvelopeHero />);
        expect(observe).not.toHaveBeenCalled();
        expect(context.clearRect).not.toHaveBeenCalled();
    });

    it("sizes, animates, pauses and cleans up when visibility changes", () => {
        let onIntersection: IntersectionObserverCallback | undefined;
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
            fillStyle: "",
        };
        vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false } as MediaQueryList);
        vi.stubGlobal(
            "IntersectionObserver",
            class {
                constructor(callback: IntersectionObserverCallback) {
                    onIntersection = callback;
                }
                observe = observe;
                disconnect = disconnect;
            },
        );
        vi.stubGlobal("requestAnimationFrame", frame);
        vi.stubGlobal("cancelAnimationFrame", cancel);
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
            context as unknown as CanvasRenderingContext2D,
        );
        const { container, unmount } = renderUI(<EnvelopeHero />);
        const stage = container.querySelector<HTMLElement>(".env-hero")!;
        Object.defineProperty(stage, "clientWidth", { configurable: true, value: 300 });
        Object.defineProperty(stage, "clientHeight", { configurable: true, value: 120 });

        onIntersection!(
            [{ isIntersecting: true } as IntersectionObserverEntry],
            {} as IntersectionObserver,
        );
        const canvas = container.querySelector<HTMLElement>("canvas")!;
        expect(observe).toHaveBeenCalledWith(stage);
        expect(canvas).toHaveProperty("width", 300);
        expect(canvas).toHaveProperty("height", 120);
        expect(frame).toHaveBeenCalled();

        onIntersection!(
            [{ isIntersecting: false } as IntersectionObserverEntry],
            {} as IntersectionObserver,
        );
        expect(cancel).toHaveBeenCalledWith(42);
        unmount();
        expect(disconnect).toHaveBeenCalled();
        expect(cancel).toHaveBeenCalled();
    });

    it("draws spawned coins on animation frames", () => {
        let onIntersection: IntersectionObserverCallback | undefined;
        let animation: FrameRequestCallback | undefined;
        const context = {
            clearRect: vi.fn(),
            beginPath: vi.fn(),
            arc: vi.fn(),
            fill: vi.fn(),
            globalAlpha: 1,
            fillStyle: "",
        };
        vi.spyOn(window, "matchMedia").mockReturnValue({ matches: false } as MediaQueryList);
        vi.spyOn(window, "getComputedStyle").mockReturnValue({
            getPropertyValue: (name: string) => (name === "--m-text" ? "#111" : "#f00"),
        } as CSSStyleDeclaration);
        vi.stubGlobal(
            "IntersectionObserver",
            class {
                constructor(callback: IntersectionObserverCallback) {
                    onIntersection = callback;
                }
                observe() {}
                disconnect() {}
            },
        );
        vi.stubGlobal(
            "requestAnimationFrame",
            vi.fn((callback: FrameRequestCallback) => {
                animation = callback;
                return 7;
            }),
        );
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
            context as unknown as CanvasRenderingContext2D,
        );
        vi.spyOn(Math, "random").mockReturnValue(0.5);
        const { container } = renderUI(<EnvelopeHero />);
        const stage = container.querySelector<HTMLElement>(".env-hero")!;
        Object.defineProperty(stage, "clientWidth", { configurable: true, value: 300 });
        Object.defineProperty(stage, "clientHeight", { configurable: true, value: 200 });
        stage.getBoundingClientRect = () => DOMRect.fromRect({ x: 0 });
        stage.querySelectorAll<HTMLElement>(".env-hero__pocket").forEach((pocket, index) => {
            pocket.getBoundingClientRect = () => DOMRect.fromRect({ x: index * 50, width: 40 });
        });

        onIntersection!(
            [{ isIntersecting: true } as IntersectionObserverEntry],
            {} as IntersectionObserver,
        );
        animation!(301);
        expect(context.clearRect).toHaveBeenCalled();
        expect(context.arc).toHaveBeenCalled();
        expect(context.fill).toHaveBeenCalled();
        expect(context.fillStyle).toBe("#111");
        // Advance the same coin through the floor: expired particles are removed
        // instead of being drawn indefinitely.
        for (let timestamp = 602; timestamp < 30000; timestamp += 301) animation!(timestamp);
    });
});
