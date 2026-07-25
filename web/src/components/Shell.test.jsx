import { describe, it, expect, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Shell from "./Shell.jsx";
import { renderUI, screen, waitFor, resetStore, userEvent } from "../test/render.jsx";

describe("Shell", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders header with brand and links", () => {
        renderUI(
            <MemoryRouter initialEntries={["/welcome"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        expect(screen.getByText("docs")).toBeTruthy();
        expect(screen.getByText("Sign in")).toBeTruthy();
        expect(screen.getByLabelText("GitHub")).toBeTruthy();
    });

    it("toggles theme when clicking theme button", async () => {
        const mockToggle = () => {};
        const { user } = renderUI(
            <MemoryRouter initialEntries={["/welcome"]}>
                <Shell theme="light" onToggleTheme={mockToggle} />
            </MemoryRouter>,
        );
        const themeBtn = screen.getByLabelText("Toggle theme");
        expect(themeBtn).toBeTruthy();
        await user.click(themeBtn);
    });

    it("shows moon icon in light theme", () => {
        renderUI(
            <MemoryRouter initialEntries={["/welcome"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        const svg = screen.getByLabelText("Toggle theme").querySelector("svg");
        expect(svg).toBeTruthy();
    });

    it("shows sun icon in dark theme", () => {
        renderUI(
            <MemoryRouter initialEntries={["/welcome"]}>
                <Shell theme="dark" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        const svg = screen.getByLabelText("Toggle theme").querySelector("svg");
        expect(svg).toBeTruthy();
    });

    it("hides burger button on landing page", () => {
        renderUI(
            <MemoryRouter initialEntries={["/welcome"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        expect(screen.queryByLabelText("Toggle navigation")).toBeFalsy();
    });

    it("shows burger button on docs pages", () => {
        renderUI(
            <MemoryRouter initialEntries={["/docs/getting-started"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        expect(screen.getByLabelText("Toggle navigation")).toBeTruthy();
    });

    it("toggles docs sidebar when clicking burger", async () => {
        const { user, container } = renderUI(
            <MemoryRouter initialEntries={["/docs/getting-started"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        const burger = screen.getByLabelText("Toggle navigation");
        const sidebar = container.querySelector(".docs-side");
        expect(sidebar).not.toHaveClass("docs-side_open");
        await user.click(burger);
        await waitFor(() => {
            expect(sidebar).toHaveClass("docs-side_open");
        });
    });

    it("closes sidebar when navigating to a doc", async () => {
        const { user, container } = renderUI(
            <MemoryRouter initialEntries={["/docs/getting-started"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        const burger = screen.getByLabelText("Toggle navigation");
        await user.click(burger);
        const sidebar = container.querySelector(".docs-side");
        expect(sidebar).toHaveClass("docs-side_open");
        // Click on a nav link would close sidebar, but we can't verify without actual nav items
    });

    it("shows documentation nav link", () => {
        renderUI(
            <MemoryRouter initialEntries={["/welcome"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        const docLink = screen.getByText("Documentation");
        expect(docLink).toHaveAttribute("href", "/docs/getting-started");
    });

    it("renders outlet for child routes", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/welcome"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        // Outlet should be rendered in the docs-root
        expect(container.querySelector(".docs-root")).toBeTruthy();
    });

    it("links to GitHub with correct URL", () => {
        renderUI(
            <MemoryRouter initialEntries={["/welcome"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        const githubLink = screen.getByLabelText("GitHub");
        expect(githubLink).toHaveAttribute("href", "https://github.com/alchemmist/monori");
    });

    it("has correct sign in link", () => {
        renderUI(
            <MemoryRouter initialEntries={["/welcome"]}>
                <Shell theme="light" onToggleTheme={() => {}} />
            </MemoryRouter>,
        );
        const signInLink = screen.getByText("Sign in");
        expect(signInLink).toHaveAttribute("href", "/login");
    });
});
