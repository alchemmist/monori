import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom implements neither of these, and Mantine/recharts call them on mount:
// without the stubs every dropdown, modal and chart throws before it renders
window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
});

class ResizeObserverStub implements ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
}
window.ResizeObserver = ResizeObserverStub;
class IntersectionObserverStub implements IntersectionObserver {
    readonly root = null;
    readonly rootMargin = "0px";
    readonly thresholds = [0];
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
        return [];
    }
}
window.IntersectionObserver = IntersectionObserverStub;
function defineMissingMethod(target: object, name: string, value: () => unknown) {
    if (!(name in target)) {
        Object.defineProperty(target, name, { configurable: true, value, writable: true });
    }
}
defineMissingMethod(window.HTMLElement.prototype, "scrollIntoView", () => {});
defineMissingMethod(window.HTMLElement.prototype, "hasPointerCapture", () => false);
defineMissingMethod(window.HTMLElement.prototype, "releasePointerCapture", () => {});
defineMissingMethod(window.HTMLElement.prototype, "setPointerCapture", () => {});
defineMissingMethod(window.HTMLElement.prototype, "animate", () => ({
    cancel: () => {},
    finished: Promise.resolve(),
}));
window.scrollTo = () => {};
window.HTMLCanvasElement.prototype.getContext = () => null;
Object.defineProperty(window.document, "fonts", {
    configurable: true,
    value: { addEventListener() {}, removeEventListener() {} },
});

const measuredDimension = (value: string, fallback: number) => {
    const parsed = Number(value.replace("px", ""));
    return parsed === 0 || Number.isNaN(parsed) ? fallback : parsed;
};

// jsdom paints nothing, so every element measures 0×0 — recharts and the
// windowed transaction list both fall back to rendering nothing at that size.
// Give the layout a plausible viewport instead.
Object.defineProperty(window.HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get(this: HTMLElement) {
        return measuredDimension(this.style.height, 900);
    },
});
Object.defineProperty(window.HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get(this: HTMLElement) {
        return measuredDimension(this.style.width, 1200);
    },
});
window.HTMLElement.prototype.getBoundingClientRect = () =>
    DOMRect.fromRect({ x: 0, y: 0, width: 1200, height: 900 });

afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    try {
        window.localStorage.clear();
    } catch {
        // Storage may be unavailable or deliberately replaced by a throwing stub.
    }
});
