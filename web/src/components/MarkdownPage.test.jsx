import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import MarkdownPage from "./MarkdownPage.jsx";
import { renderUI, screen, waitFor, resetStore } from "../test/render.jsx";

vi.mock("./Mermaid.jsx", () => ({
    default: ({ chart, fullscreenHref }) => (
        <div data-testid="mermaid" data-chart={chart}>
            Mermaid diagram
        </div>
    ),
}));

vi.mock("../content.js", () => ({
    sectionBySlug: (slug) => {
        if (slug === "getting-started") {
            return {
                slug: "getting-started",
                title: "Getting Started",
                body: "# Getting Started\n\nThis is the intro page.",
            };
        }
        if (slug === "api") {
            return {
                slug: "api",
                title: "REST API",
                body: "# REST API\n\n[Guide](./getting-started.md) [Web](https://example.com)\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```mermaid\ngraph TD\n  A-->B\n```",
            };
        }
        return null;
    },
    neighbors: (slug) => {
        if (slug === "getting-started") {
            return { prev: null, next: { slug: "api", title: "REST API" } };
        }
        return { prev: null, next: null };
    },
    mermaidCharts: (body) => {
        const matches = [...String(body ?? "").matchAll(/```mermaid[^\n]*\n([\s\S]*?)```/g)];
        return matches.map((m) => m[1].replace(/\n$/, ""));
    },
}));

describe("MarkdownPage", () => {
    beforeEach(() => {
        resetStore();
    });

    const renderPage = (path) =>
        renderUI(
            <MemoryRouter initialEntries={[path]}>
                <Routes>
                    <Route path="/docs/:slug" element={<MarkdownPage />} />
                </Routes>
            </MemoryRouter>,
        );

    it("renders markdown headings and the neighbouring page navigation", () => {
        renderPage("/docs/getting-started");
        expect(screen.getByRole("heading", { name: "Getting Started" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /next\s*rest api/i })).toHaveAttribute(
            "href",
            "/docs/api",
        );
    });

    it("shows not found for invalid slug", async () => {
        const { user } = renderPage("/docs/nonexistent");
        expect(screen.getByRole("heading", { name: "Not found" })).toBeInTheDocument();
        expect(screen.getByText(/nonexistent/)).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: /back to the docs/i }));
        expect(screen.getByRole("heading", { name: "Getting Started" })).toBeInTheDocument();
    });

    it("turns Mermaid fences into diagrams and preserves links and tables", () => {
        const { container } = renderPage("/docs/api");
        expect(screen.getByTestId("mermaid")).toHaveAttribute("data-chart", "graph TD\n  A-->B");
        expect(container.querySelector(".md-table-wrap table")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Guide" })).toHaveAttribute(
            "href",
            "/docs/getting-started",
        );
        expect(screen.getByRole("link", { name: "Web" })).toHaveAttribute("target", "_blank");
    });

    it("scrolls to an existing hash target, otherwise resets page scroll", () => {
        const scrollIntoView = vi.fn();
        window.HTMLElement.prototype.scrollIntoView = scrollIntoView;
        const scrollSpy = vi.spyOn(window, "scrollTo");
        renderPage("/docs/getting-started#getting-started");
        expect(scrollIntoView).toHaveBeenCalled();
        renderPage("/docs/getting-started#missing");
        expect(scrollSpy).toHaveBeenCalledWith(0, 0);
        scrollSpy.mockRestore();
    });
});
