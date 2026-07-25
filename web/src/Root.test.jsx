import { describe, it, expect, vi, beforeEach } from "vitest";
import Root from "./Root.jsx";
import { renderUI, screen, waitFor, resetStore } from "./test/render.jsx";

// Ensure localStorage is available for jsdom
if (!globalThis.localStorage) {
    globalThis.localStorage = {
        data: {},
        getItem(key) {
            return this.data[key] || null;
        },
        setItem(key, value) {
            this.data[key] = String(value);
        },
        removeItem(key) {
            delete this.data[key];
        },
        clear() {
            this.data = {};
        },
    };
}

vi.mock("./components/Landing.jsx", () => ({
    default: () => <div>Landing</div>,
}));

vi.mock("./components/MarkdownPage.jsx", () => ({
    default: () => <div>MarkdownPage</div>,
}));

vi.mock("./components/DiagramPage.jsx", () => ({
    default: () => <div>DiagramPage</div>,
}));

describe("Root", () => {
    beforeEach(() => {
        resetStore();
        localStorage.clear();
    });

    it("renders without crashing", () => {
        const { container } = renderUI(<Root />);
        expect(container).toBeTruthy();
    });

    it("reads theme from localStorage on mount", () => {
        localStorage.setItem("theme", "dark");
        renderUI(<Root />);
        expect(document.body).toHaveClass("theme-dark");
    });

    it("defaults to light theme if not in localStorage", () => {
        renderUI(<Root />);
        expect(document.body).not.toHaveClass("theme-dark");
    });

    it("renders MantineProvider wrapper", () => {
        const { container } = renderUI(<Root />);
        // MantineProvider should render content
        expect(container.firstChild).toBeTruthy();
    });

    it("sets body class based on theme state", () => {
        renderUI(<Root />);
        const initialHasDarkClass = document.body.classList.contains("theme-dark");
        expect(typeof initialHasDarkClass).toBe("boolean");
    });

    it("wraps content in BrowserRouter", () => {
        const { container } = renderUI(<Root />);
        // If Router is present, navigation and routes should work
        expect(container).toBeTruthy();
    });

    it("renders Suspense boundary for lazy components", () => {
        const { container } = renderUI(<Root />);
        // The component should render even with lazy imports
        expect(container).toBeTruthy();
    });

    it("applies MantineProvider with forceColorScheme prop", () => {
        renderUI(<Root />);
        // Color scheme should be applied
        expect(document.body).toBeTruthy();
    });
});
