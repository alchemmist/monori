import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom implements neither of these, and Mantine/recharts call them on mount:
// without the stubs every dropdown, modal and chart throws before it renders
if (!window.matchMedia) {
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
}

class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
}
window.ResizeObserver ??= ResizeObserverStub;
window.IntersectionObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
        return [];
    }
};
window.HTMLElement.prototype.scrollIntoView ??= () => {};
window.HTMLElement.prototype.hasPointerCapture ??= () => false;
window.HTMLElement.prototype.releasePointerCapture ??= () => {};
window.HTMLElement.prototype.setPointerCapture ??= () => {};
window.HTMLElement.prototype.animate ??= () => ({ cancel: () => {} });
window.scrollTo = () => {};
window.HTMLCanvasElement.prototype.getContext = () => null;

// jsdom paints nothing, so every element measures 0×0 — recharts and the
// windowed transaction list both fall back to rendering nothing at that size.
// Give the layout a plausible viewport instead.
Object.defineProperty(window.HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get() {
        return Number(this.style.height?.replace("px", "")) || 900;
    },
});
Object.defineProperty(window.HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get() {
        return Number(this.style.width?.replace("px", "")) || 1200;
    },
});
window.HTMLElement.prototype.getBoundingClientRect = function () {
    return { x: 0, y: 0, top: 0, left: 0, right: 1200, bottom: 900, width: 1200, height: 900 };
};

afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    try {
        window.localStorage?.clear?.();
    } catch {
        // Storage may be unavailable or deliberately replaced by a throwing stub.
    }
});
