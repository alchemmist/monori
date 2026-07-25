import { describe, it, expect, beforeEach, vi } from "vitest";
import Mermaid from "./Mermaid.jsx";
import { renderUI, screen, waitFor, resetStore } from "../test/render.jsx";

vi.mock("./useMermaidSvg.js", () => ({
    useMermaidSvg: (chart) => {
        if (chart === "broken") {
            return { svg: null, failed: true };
        }
        if (chart === "loading") {
            return { svg: null, failed: false };
        }
        return { svg: '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" /></svg>', failed: false };
    },
}));

describe("Mermaid", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders diagram when svg is available", () => {
        renderUI(<Mermaid chart="graph TD\n  A-->B" fullscreenHref={null} />);
        const figure = screen.getByRole("img");
        expect(figure).toBeTruthy();
        expect(figure.querySelector("svg")).toBeTruthy();
    });

    it("shows source code when diagram failed", () => {
        renderUI(<Mermaid chart="broken" fullscreenHref={null} />);
        expect(screen.getByText("broken")).toBeTruthy();
    });

    it("shows source code while loading", () => {
        renderUI(<Mermaid chart="loading" fullscreenHref={null} />);
        const pre = screen.getByText("loading");
        expect(pre.tagName).toBe("CODE");
    });

    it("renders full screen link when href provided", () => {
        renderUI(<Mermaid chart="graph TD\n  A-->B" fullscreenHref="/docs/api/diagram/0" />);
        const link = screen.getByText("Full screen");
        expect(link).toHaveAttribute("href", "/docs/api/diagram/0");
        expect(link).toHaveAttribute("target", "_blank");
    });

    it("does not render full screen link when href is null", () => {
        renderUI(<Mermaid chart="graph TD\n  A-->B" fullscreenHref={null} />);
        expect(screen.queryByText("Full screen")).toBeFalsy();
    });

    it("preserves html structure for svg diagram", () => {
        const { container } = renderUI(
            <Mermaid chart="graph TD\n  A-->B" fullscreenHref={null} />,
        );
        const figure = container.querySelector("figure.md-mermaid");
        expect(figure).toBeTruthy();
        const canvas = figure.querySelector(".md-mermaid__canvas");
        expect(canvas).toBeTruthy();
    });

    it("uses figure element for diagrams", () => {
        const { container } = renderUI(
            <Mermaid chart="graph TD\n  A-->B" fullscreenHref={null} />,
        );
        expect(container.querySelector("figure")).toBeTruthy();
    });

    it("uses pre for source code display on failure", () => {
        const { container } = renderUI(<Mermaid chart="broken" fullscreenHref={null} />);
        expect(container.querySelector("pre.md-mermaid-src")).toBeTruthy();
    });

    it("renders svg with dangerouslySetInnerHTML", () => {
        const { container } = renderUI(
            <Mermaid chart="graph TD\n  A-->B" fullscreenHref={null} />,
        );
        const canvas = container.querySelector(".md-mermaid__canvas");
        expect(canvas.innerHTML).toContain("<svg");
    });
});
