import { describe, it, expect, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Landing from "./Landing.jsx";
import { renderUI, screen, resetStore } from "../test/render.jsx";

describe("Landing", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders hero section", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText(/Your budget, to the last kopeck/)).toBeTruthy();
    });

    it("has sign in call to action", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        const signInBtn = screen.getByText("Sign in");
        expect(signInBtn).toHaveAttribute("href", "/login");
    });

    it("has demo call to action", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        const demoBtn = screen.getByText("Try the live demo");
        expect(demoBtn).toHaveAttribute("href", "/demo");
    });

    it("has get started documentation link", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        const getStartedBtns = screen.getAllByText("Get started");
        expect(getStartedBtns.length).toBeGreaterThan(0);
        expect(getStartedBtns[0]).toHaveAttribute("href", "/docs/getting-started");
    });

    it("has github link", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        const githubLink = screen.getByText("GitHub");
        expect(githubLink).toHaveAttribute("href", "https://github.com/alchemmist/monori");
    });

    it("renders feature sections", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText("Envelope budgeting")).toBeTruthy();
        expect(screen.getByText("Integer kopecks")).toBeTruthy();
        expect(screen.getByText("Statement import")).toBeTruthy();
    });

    it("renders math model section", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText("The whole model in three lines")).toBeTruthy();
    });

    it("renders bloom section with minori reference", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText(/minori/)).toBeTruthy();
    });

    it("has deploy section with docker link", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText("Deploy monori")).toBeTruthy();
    });

    it("has footer with links", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText("Getting started")).toBeTruthy();
        expect(screen.getByText("API")).toBeTruthy();
        expect(screen.getByText("Contributing")).toBeTruthy();
    });

    it("links to documentation pages from feature tiles", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        const envelopLink = screen.getByText("Envelope budgeting").closest("a");
        expect(envelopLink).toHaveAttribute("href", "/docs/budgeting");
    });

    it("renders self-hosted feature", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText("Self-hosted & private")).toBeTruthy();
        expect(screen.getByText("Your data never leaves it")).toBeTruthy();
    });

    it("renders multi-user feature", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText("Multi-user")).toBeTruthy();
    });

    it("renders open source feature", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText("Open source")).toBeTruthy();
    });

    it("renders full rest api feature", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText("Full REST API")).toBeTruthy();
        expect(screen.getByText("/api/snapshot")).toBeTruthy();
    });

    it("renders backup feature", () => {
        renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        expect(screen.getByText("One-file backup")).toBeTruthy();
    });

    it("has configuration link", () => {
        const { container } = renderUI(
            <MemoryRouter>
                <Landing />
            </MemoryRouter>,
        );
        const configLinks = screen.getAllByText("Configuration");
        expect(configLinks.length).toBeGreaterThan(0);
    });
});
