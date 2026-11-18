import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { renderUI, screen } from "../test/render.jsx";
import Landing from "./Landing.jsx";

vi.mock("./Meadow.jsx", () => ({ default: () => <div /> }));
vi.mock("./GlyphFlower.jsx", () => ({ default: () => <div /> }));
vi.mock("./Wordmark.jsx", () => ({ default: () => <div /> }));
vi.mock("./EnvelopeHero.jsx", () => ({ default: () => <div /> }));

describe("Landing", () => {
    it("offers the product entry points and documentation", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByRole("heading", { name: /your budget/i })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
        expect(screen.getByRole("link", { name: /try the live demo/i })).toHaveAttribute(
            "href",
            "/demo",
        );
        expect(screen.getAllByRole("link", { name: /get started/i })[0]).toHaveAttribute(
            "href",
            "/docs/getting-started",
        );
        expect(screen.getByText("The whole model in three lines")).toBeInTheDocument();
        expect(screen.getByText("Run it with one command.")).toBeInTheDocument();
        expect(screen.getAllByRole("link", { name: "GitHub" })).toHaveLength(2);
        expect(screen.getAllByRole("link", { name: "GitHub" })[0]).toHaveAttribute(
            "href",
            "https://github.com/alchemmist/monori",
        );
        expect(screen.getByRole("link", { name: /deploy monori/i })).toHaveAttribute(
            "href",
            "/docs/getting-started",
        );
    });
});
