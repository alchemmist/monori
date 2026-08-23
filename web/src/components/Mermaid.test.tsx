import { describe, expect, it, vi } from "vitest";
import { renderUI, screen } from "../test/render.jsx";
import Mermaid from "./Mermaid.jsx";

vi.mock("./useMermaidSvg.js", () => ({ useMermaidSvg: vi.fn() }));
import { useMermaidSvg } from "./useMermaidSvg.js";

describe("Mermaid", () => {
    it("keeps source readable while a chart is unavailable", () => {
        vi.mocked(useMermaidSvg).mockReturnValue({ svg: "", failed: false });
        renderUI(<Mermaid chart="flowchart LR" />);
        expect(screen.getByText("flowchart LR")).toBeInTheDocument();
    });

    it("renders sanitized engine output and an optional full-screen link", () => {
        vi.mocked(useMermaidSvg).mockReturnValue({
            svg: '<svg aria-label="chart"></svg>',
            failed: false,
        });
        renderUI(<Mermaid chart="x" fullscreenHref="/diagram/x" />);
        expect(screen.getByRole("img")).toContainHTML("svg");
        expect(screen.getByRole("link", { name: /full screen/i })).toHaveAttribute(
            "href",
            "/diagram/x",
        );
    });

    it("falls back after an engine failure", () => {
        vi.mocked(useMermaidSvg).mockReturnValue({ svg: "<svg />", failed: true });
        renderUI(<Mermaid chart="bad chart" />);
        expect(screen.getByText("bad chart")).toBeInTheDocument();
    });
});
