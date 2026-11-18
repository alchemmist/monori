import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import MarkdownPage from "./MarkdownPage.jsx";
import { renderUI, screen, resetStore } from "../test/render.jsx";

vi.mock("./Mermaid.jsx", () => ({
    default: ({ chart, fullscreenHref }: { chart: string; fullscreenHref?: string }) => (
        <div data-testid="mermaid" data-chart={chart} data-href={fullscreenHref ?? ""}>
            Mermaid diagram
        </div>
    ),
}));

// only the page catalogue is stubbed — mermaidCharts is the real parser, so the
// diagram indices the page hands out are the ones production would compute
vi.mock("../content.js", async (importOriginal) => {
    const actual = await importOriginal<typeof import("../content.js")>();
    const sections = [
        {
            slug: "getting-started",
            title: "Getting Started",
            body: "# Getting Started\n\n## Second stop\n\nThis is the intro page.",
        },
        {
            slug: "api",
            title: "REST API",
            body: [
                "# REST API",
                "",
                "[Guide](./getting-started.md) [Home](./README.md) [Web](https://example.com)",
                "",
                "| A | B |",
                "|---|---|",
                "| 1 | 2 |",
                "",
                "```mermaid\ngraph TD\n  A-->B\n```",
                "",
                "```mermaid\ngraph LR\n  C-->D\n```",
                "",
                "```js\nconst x = 1;\n```",
            ].join("\n"),
        },
    ];
    return {
        ...actual,
        NAV: [{ group: "Docs", items: sections }],
        sectionBySlug: (slug: string) => sections.find((s) => s.slug === slug),
        neighbors: (slug: string) => {
            const i = sections.findIndex((s) => s.slug === slug);
            return {
                prev: i > 0 ? sections[i - 1] : null,
                next: i >= 0 && i < sections.length - 1 ? sections[i + 1] : null,
            };
        },
    };
});

describe("MarkdownPage", () => {
    beforeEach(() => {
        resetStore();
    });

    const renderPage = (path: string) =>
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
        expect(screen.queryByRole("link", { name: /previous/i })).not.toBeInTheDocument();
    });

    it("shows not found for invalid slug", async () => {
        const { user } = renderPage("/docs/nonexistent");
        expect(screen.getByRole("heading", { name: "Not found" })).toBeInTheDocument();
        expect(screen.getByText(/nonexistent/)).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: /back to the docs/i }));
        expect(screen.getByRole("heading", { name: "Getting Started" })).toBeInTheDocument();
    });

    it("rewrites in-repo markdown links, sending README to the docs entry page", () => {
        renderPage("/docs/api");
        expect(screen.getByRole("link", { name: "Guide" })).toHaveAttribute(
            "href",
            "/docs/getting-started",
        );
        expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
            "href",
            "/docs/getting-started",
        );
        expect(screen.getByRole("link", { name: "Web" })).toHaveAttribute("target", "_blank");
        expect(screen.getByRole("link", { name: "Web" })).toHaveAttribute(
            "href",
            "https://example.com",
        );
    });

    it("turns Mermaid fences into diagrams, each linking to its own full-screen view", () => {
        const { container } = renderPage("/docs/api");
        const diagrams = screen.getAllByTestId("mermaid");
        expect(diagrams).toHaveLength(2);
        expect(diagrams[0]).toHaveAttribute("data-chart", "graph TD\n  A-->B");
        expect(diagrams[0]).toHaveAttribute("data-href", "/docs/api/diagram/0");
        expect(diagrams[1]).toHaveAttribute("data-chart", "graph LR\n  C-->D");
        expect(diagrams[1]).toHaveAttribute("data-href", "/docs/api/diagram/1");
        // a non-mermaid fence keeps its plain <pre>
        expect(container.querySelector<HTMLElement>("pre code.language-js")!).toBeInTheDocument();
        expect(container.querySelector<HTMLElement>(".md-table-wrap table")!).toBeInTheDocument();
    });

    it("scrolls to an existing hash target instead of resetting the page scroll", () => {
        const scrollIntoView = vi.fn();
        window.HTMLElement.prototype.scrollIntoView = scrollIntoView;
        const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});

        renderPage("/docs/getting-started#second-stop");
        expect(scrollIntoView).toHaveBeenCalledOnce();
        expect(scrollTo).not.toHaveBeenCalled();
    });

    it("resets the page scroll when the hash points at nothing", () => {
        const scrollIntoView = vi.fn();
        window.HTMLElement.prototype.scrollIntoView = scrollIntoView;
        const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});

        renderPage("/docs/getting-started#missing");
        expect(scrollTo).toHaveBeenCalledWith(0, 0);
        expect(scrollIntoView).not.toHaveBeenCalled();
    });
});
