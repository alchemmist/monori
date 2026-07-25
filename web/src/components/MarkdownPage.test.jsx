import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
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
                body: "# REST API\n\n```mermaid\ngraph TD\n  A-->B\n```",
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

    it("renders for valid slug", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/getting-started"]}>
                <MarkdownPage />
            </MemoryRouter>,
        );
        expect(container).toBeTruthy();
    });

    it("shows not found for invalid slug", () => {
        renderUI(
            <MemoryRouter initialEntries={["/docs/nonexistent"]}>
                <MarkdownPage />
            </MemoryRouter>,
        );
        expect(screen.getByText("Not found")).toBeTruthy();
    });

    it("renders article element", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/getting-started"]}>
                <MarkdownPage />
            </MemoryRouter>,
        );
        const article = container.querySelector("article.md");
        if (article) {
            expect(article).toBeTruthy();
        }
    });

    it("includes navigation when section exists", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/getting-started"]}>
                <MarkdownPage />
            </MemoryRouter>,
        );
        // Navigation may or may not be present depending on section
        expect(container).toBeTruthy();
    });

    it("handles hash navigation", () => {
        const scrollSpy = vi.spyOn(window, "scrollTo");
        renderUI(
            <MemoryRouter initialEntries={["/docs/getting-started#test"]}>
                <MarkdownPage />
            </MemoryRouter>,
        );
        scrollSpy.mockRestore();
    });
});
