import { describe, expect, it, vi, beforeEach } from "vitest";
import EnvelopeHero from "./EnvelopeHero.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("EnvelopeHero", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("renders the main container with env-hero class", () => {
        const { container } = renderUI(<EnvelopeHero />);
        expect(container.querySelector(".env-hero")).toBeInTheDocument();
    });

    it("has aria-hidden attribute to hide from accessibility tree", () => {
        const { container } = renderUI(<EnvelopeHero />);
        expect(container.querySelector(".env-hero")).toHaveAttribute("aria-hidden", "true");
    });

    it("renders canvas element", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const canvas = container.querySelector("canvas");
        expect(canvas).toBeInTheDocument();
        expect(canvas).toHaveClass("env-hero__canvas");
    });

    it("renders all four envelopes", () => {
        renderUI(<EnvelopeHero />);
        expect(screen.getByText("Groceries")).toBeInTheDocument();
        expect(screen.getByText("Transport")).toBeInTheDocument();
        expect(screen.getByText("Eating out")).toBeInTheDocument();
        expect(screen.getByText("Savings")).toBeInTheDocument();
    });

    it("renders envelope amounts", () => {
        renderUI(<EnvelopeHero />);
        expect(screen.getByText("12 000")).toBeInTheDocument();
        expect(screen.getByText("4 000")).toBeInTheDocument();
        expect(screen.getByText("6 000")).toBeInTheDocument();
        expect(screen.getByText("20 000")).toBeInTheDocument();
    });

    it("renders envelope row container", () => {
        const { container } = renderUI(<EnvelopeHero />);
        expect(container.querySelector(".env-hero__row")).toBeInTheDocument();
    });

    it("renders envelope containers with env-hero__env class", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const envs = container.querySelectorAll(".env-hero__env");
        expect(envs.length).toBe(4);
    });

    it("applies is-hot class to Eating out envelope", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const eatingOut = Array.from(container.querySelectorAll(".env-hero__env")).find((el) =>
            el.textContent.includes("Eating out"),
        );
        expect(eatingOut).toHaveClass("is-hot");
    });

    it("does not apply is-hot class to non-hot envelopes", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const groceries = Array.from(container.querySelectorAll(".env-hero__env")).find((el) =>
            el.textContent.includes("Groceries"),
        );
        expect(groceries).not.toHaveClass("is-hot");
    });

    it("renders pocket elements for each envelope", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const pockets = container.querySelectorAll(".env-hero__pocket");
        expect(pockets.length).toBe(4);
    });

    it("amounts have num class", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const amts = container.querySelectorAll(".env-hero__amt");
        expect(amts.length).toBe(4);
        amts.forEach((amt) => {
            expect(amt).toHaveClass("num");
        });
    });

    it("envelope names have env-hero__name class", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const names = container.querySelectorAll(".env-hero__name");
        expect(names.length).toBe(4);
    });

    it("cleanup happens on unmount", () => {
        const { unmount } = renderUI(<EnvelopeHero />);
        unmount();
        // Component should not throw on unmount
    });

    it("renders amounts within pockets", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const pockets = container.querySelectorAll(".env-hero__pocket");
        expect(pockets[0].textContent).toContain("12 000");
        expect(pockets[1].textContent).toContain("4 000");
        expect(pockets[2].textContent).toContain("6 000");
        expect(pockets[3].textContent).toContain("20 000");
    });

    it("renders names after pockets", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const envs = container.querySelectorAll(".env-hero__env");
        expect(envs[0].querySelector(".env-hero__name")?.textContent).toBe("Groceries");
        expect(envs[1].querySelector(".env-hero__name")?.textContent).toBe("Transport");
        expect(envs[2].querySelector(".env-hero__name")?.textContent).toBe("Eating out");
        expect(envs[3].querySelector(".env-hero__name")?.textContent).toBe("Savings");
    });

    it("canvas element is accessible by ref", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const canvas = container.querySelector("canvas.env-hero__canvas");
        expect(canvas).toBeTruthy();
        expect(canvas.getContext).toBeDefined();
    });

    it("stage container is accessible by ref", () => {
        const { container } = renderUI(<EnvelopeHero />);
        const stage = container.querySelector(".env-hero");
        expect(stage).toBeTruthy();
    });
});
