import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fireEvent, renderUI, screen } from "../test/render.jsx";

vi.mock("../content.js", () => ({
    sectionBySlug: (slug: string) =>
        slug === "guide" ? { title: "Guide", body: "diagram source" } : null,
    mermaidCharts: (body: string) => (body ? ["first chart", "second chart"] : []),
}));
vi.mock("./useMermaidSvg.js", () => ({
    naturalSize: vi.fn(() => ({ width: 800, height: 400 })),
    useMermaidSvg: vi.fn(),
}));

import DiagramPage from "./DiagramPage.jsx";
import { naturalSize, useMermaidSvg } from "./useMermaidSvg.js";

function renderDiagram(path = "/docs/guide/diagram/0") {
    return renderUI(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/docs/:slug/diagram/:index" element={<DiagramPage />} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("DiagramPage", () => {
    it("renders the selected diagram, fits it to the stage and links back", () => {
        vi.mocked(useMermaidSvg).mockReturnValue({
            svg: '<svg viewBox="0 0 800 400"></svg>',
            failed: false,
        });
        const { container } = renderDiagram();

        expect(useMermaidSvg).toHaveBeenCalledWith("first chart");
        expect(naturalSize).toHaveBeenCalled();
        expect(screen.getByRole("link", { name: /guide/i })).toHaveAttribute("href", "/docs/guide");
        expect(container.querySelector<HTMLElement>(".diagram-page__canvas")!).toHaveStyle({
            width: "800px",
            height: "400px",
            transform: "translate(200px, 250px) scale(1)",
        });
    });

    it("zooms through buttons, keyboard, wheel and restores fitted view", () => {
        vi.mocked(useMermaidSvg).mockReturnValue({ svg: "<svg></svg>", failed: false });
        const { container } = renderDiagram();
        const stage = container.querySelector<HTMLElement>(".diagram-page__stage")!;
        const zoom = () => screen.getByText(/%$/).textContent;

        expect(zoom()).toBe("100%");
        fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
        expect(zoom()).toBe("83%");
        fireEvent.keyDown(window, { key: "+" });
        expect(zoom()).toBe("100%");
        fireEvent.wheel(stage, { clientX: 600, clientY: 450, deltaY: -1000 });
        expect(zoom()).toBe("448%");
        fireEvent.click(screen.getByRole("button", { name: "Fit to screen" }));
        expect(zoom()).toBe("100%");
    });

    it("pans with a primary pointer drag and ignores other buttons", () => {
        vi.mocked(useMermaidSvg).mockReturnValue({ svg: "<svg></svg>", failed: false });
        const { container } = renderDiagram();
        const stage = container.querySelector<HTMLElement>(".diagram-page__stage")!;
        const canvas = container.querySelector<HTMLElement>(".diagram-page__canvas")!;

        fireEvent.pointerDown(stage, { button: 2, pointerId: 1, clientX: 20, clientY: 30 });
        fireEvent.pointerMove(stage, { pointerId: 1, clientX: 60, clientY: 70 });
        expect(stage).not.toHaveClass("diagram-page__stage_dragging");
        expect(canvas).toHaveStyle({ transform: "translate(200px, 250px) scale(1)" });

        fireEvent.pointerDown(stage, { button: 0, pointerId: 1, clientX: 20, clientY: 30 });
        expect(stage).toHaveClass("diagram-page__stage_dragging");
        fireEvent.pointerMove(stage, { pointerId: 1, clientX: 60, clientY: 70 });
        expect(canvas).toHaveStyle({ transform: "translate(240px, 290px) scale(1)" });
        fireEvent.pointerUp(stage, { pointerId: 1 });
        expect(stage).not.toHaveClass("diagram-page__stage_dragging");
    });

    it("explains missing and failed diagrams", () => {
        vi.mocked(useMermaidSvg).mockReturnValue({ svg: "", failed: false });
        const { unmount } = renderDiagram("/docs/guide/diagram/4");
        expect(screen.getByText(/no such diagram/i)).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /back to the page/i })).toHaveAttribute(
            "href",
            "/docs/guide",
        );

        vi.mocked(useMermaidSvg).mockReturnValue({ svg: "", failed: true });
        unmount();
        renderDiagram("/docs/guide/diagram/0");
        expect(screen.getByText(/could not be rendered/i)).toBeInTheDocument();
    });
});
