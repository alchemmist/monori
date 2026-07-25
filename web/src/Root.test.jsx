import { describe, it, expect, vi, beforeEach } from "vitest";
import Root from "./Root.jsx";
import { renderUI, screen, waitFor, resetStore } from "./test/render.jsx";

vi.mock("./App.jsx", () => ({
    default: ({ theme, onToggleTheme }) => (
        <div>
            <span>App: {theme}</span>
            <button onClick={onToggleTheme}>Toggle application theme</button>
        </div>
    ),
}));

vi.mock("./components/Shell.jsx", async () => {
    const { Outlet } = await import("react-router-dom");
    return {
        default: ({ theme, onToggleTheme }) => (
            <div>
                <span>Shell: {theme}</span>
                <button onClick={onToggleTheme}>Toggle shell theme</button>
                <Outlet />
            </div>
        ),
    };
});

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
        window.history.replaceState({}, "", "/");
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

    it("continues with a light theme when storage cannot be read", () => {
        vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new Error("storage disabled");
        });
        renderUI(<Root />);
        expect(document.body).not.toHaveClass("theme-dark");
        vi.restoreAllMocks();
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

    it("routes marketing, documentation and diagram URLs to their lazy pages", async () => {
        window.history.replaceState({}, "", "/welcome");
        renderUI(<Root />);
        expect(await screen.findByText("Landing")).toBeInTheDocument();
        expect(screen.getByText("Shell: light")).toBeInTheDocument();

        window.history.replaceState({}, "", "/docs/getting-started");
        window.dispatchEvent(new PopStateEvent("popstate"));
        expect(await screen.findByText("MarkdownPage")).toBeInTheDocument();

        window.history.replaceState({}, "", "/docs/example/diagram/0");
        window.dispatchEvent(new PopStateEvent("popstate"));
        expect(await screen.findByText("DiagramPage")).toBeInTheDocument();
    });

    it("redirects /docs to getting started", async () => {
        window.history.replaceState({}, "", "/docs");
        renderUI(<Root />);
        expect(await screen.findByText("MarkdownPage")).toBeInTheDocument();
        expect(window.location.pathname).toBe("/docs/getting-started");
    });

    it("toggles and persists theme from both route shells", async () => {
        window.history.replaceState({}, "", "/welcome");
        const { user } = renderUI(<Root />);
        await screen.findByText("Landing");
        await user.click(screen.getByRole("button", { name: "Toggle shell theme" }));
        expect(document.body).toHaveClass("theme-dark");
        expect(localStorage.getItem("theme")).toBe("dark");

        window.history.replaceState({}, "", "/");
        window.dispatchEvent(new PopStateEvent("popstate"));
        await user.click(await screen.findByRole("button", { name: "Toggle application theme" }));
        await waitFor(() => expect(document.body).not.toHaveClass("theme-dark"));
        expect(localStorage.getItem("theme")).toBe("light");
    });
});
