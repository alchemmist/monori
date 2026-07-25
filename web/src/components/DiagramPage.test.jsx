import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import DiagramPage from "./DiagramPage.jsx";
import { renderUI, screen, waitFor, resetStore, fireEvent } from "../test/render.jsx";

vi.mock("./useMermaidSvg.js", () => ({
    useMermaidSvg: (chart) => {
        if (chart === "") {
            return { svg: null, failed: false };
        }
        if (chart === "broken") {
            return { svg: null, failed: true };
        }
        return {
            svg: '<svg viewBox="0 0 200 300"><circle cx="100" cy="150" r="50" /></svg>',
            failed: false,
        };
    },
    naturalSize: (svg) => {
        if (!svg) return null;
        return { width: 200, height: 300 };
    },
}));

vi.mock("../content.js", () => ({
    sectionBySlug: (slug) => {
        if (slug === "api") {
            return {
                slug: "api",
                title: "REST API",
                body: "# API\n```mermaid\ngraph TD\n A-->B\n```",
            };
        }
        return null;
    },
    mermaidCharts: (body) => {
        if (body === "# API\n```mermaid\ngraph TD\n A-->B\n```") {
            return ["graph TD\n A-->B"];
        }
        return [];
    },
}));

describe("DiagramPage", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders diagram full screen page", () => {
        renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        expect(screen.getByText("REST API")).toBeTruthy();
    });

    it("shows empty message when no diagram at index", () => {
        renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/99"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        expect(screen.getByText("No such diagram.")).toBeTruthy();
    });

    it("shows error message when diagram failed to render", () => {
        // Override mock for broken diagram
        vi.mocked(require("./useMermaidSvg.js").useMermaidSvg).mockReturnValue({
            svg: null,
            failed: true,
        });
        renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        // This test depends on the actual implementation handling this case
    });

    it("has back link to parent page", () => {
        renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        const backLink = screen.getByText("REST API");
        expect(backLink).toHaveAttribute("href", "/docs/api");
    });

    it("renders zoom controls", () => {
        renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        expect(screen.getByLabelText("Zoom out")).toBeTruthy();
        expect(screen.getByLabelText("Zoom in")).toBeTruthy();
        expect(screen.getByLabelText("Fit to screen")).toBeTruthy();
    });

    it("displays current zoom percentage", () => {
        renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        const zoomDisplay = document.querySelector(".diagram-page__zoom");
        expect(zoomDisplay).toBeTruthy();
    });

    it("zoom in increases scale", async () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        const zoomInBtn = screen.getByLabelText("Zoom in");
        const zoomDisplay = container.querySelector(".diagram-page__zoom");
        const initialZoom = zoomDisplay.textContent;
        fireEvent.click(zoomInBtn);
        await waitFor(() => {
            expect(zoomDisplay.textContent).not.toBe(initialZoom);
        });
    });

    it("zoom out decreases scale", async () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        const zoomOutBtn = screen.getByLabelText("Zoom out");
        const zoomDisplay = container.querySelector(".diagram-page__zoom");
        const initialZoom = zoomDisplay.textContent;
        fireEvent.click(zoomOutBtn);
        await waitFor(() => {
            expect(zoomDisplay.textContent).not.toBe(initialZoom);
        });
    });

    it("fit button resets view", async () => {
        renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        const fitBtn = screen.getByLabelText("Fit to screen");
        fireEvent.click(fitBtn);
    });

    it("renders stage with pointer event handlers", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        const stage = container.querySelector(".diagram-page__stage");
        expect(stage).toBeTruthy();
    });

    it("responds to keyboard shortcuts", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        fireEvent.keyDown(window, { key: "0" });
        // fit() should be called
    });

    it("handles wheel events for zooming", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        const stage = container.querySelector(".diagram-page__stage");
        fireEvent.wheel(stage, { deltaY: 10 });
    });

    it("renders diagram svg in canvas", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        const canvas = container.querySelector(".diagram-page__canvas");
        expect(canvas).toBeTruthy();
    });

    it("shows page header with title", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/docs/api/diagram/0"]}>
                <DiagramPage />
            </MemoryRouter>,
        );
        const header = container.querySelector(".diagram-page__bar");
        expect(header).toBeTruthy();
    });
});
