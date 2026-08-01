import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { Moon, Sun } from "@gravity-ui/icons";
import Shell from "./Shell.jsx";
import { renderUI, screen, waitFor, resetStore } from "../test/render.jsx";
import type { ComponentProps, ComponentType, SVGProps } from "react";

function renderShell(path: string, props: Partial<ComponentProps<typeof Shell>> = {}) {
    return renderUI(
        <MemoryRouter initialEntries={[path]}>
            <Shell theme="light" onToggleTheme={() => {}} {...props} />
        </MemoryRouter>,
    );
}

/** The glyph inside the theme toggle, as markup, so Sun and Moon can be told apart. */
function toggleGlyph() {
    return screen.getByLabelText("Toggle theme").querySelector<HTMLElement>("svg")!.innerHTML;
}

function renderIcon(Icon: ComponentType<SVGProps<SVGSVGElement>>) {
    const { container, unmount } = renderUI(<Icon width={17} height={17} />);
    const svg = container.querySelector<HTMLElement>("svg")!.innerHTML;
    unmount();
    return svg;
}

describe("Shell", () => {
    beforeEach(() => {
        resetStore();
    });

    it("renders the brand and the outbound header links", () => {
        renderShell("/welcome");
        expect(screen.getByText("docs")).toBeInTheDocument();
        expect(screen.getByText("Sign in")).toHaveAttribute("href", "/login");
        expect(screen.getByLabelText("GitHub")).toHaveAttribute(
            "href",
            "https://github.com/alchemmist/monori",
        );
        expect(screen.getByText("Documentation")).toHaveAttribute("href", "/docs/getting-started");
    });

    it("offers to go dark in the light theme and to go light in the dark one", () => {
        const moon = renderIcon(Moon);
        const sun = renderIcon(Sun);
        expect(moon).not.toBe(sun);

        const light = renderShell("/welcome", { theme: "light" });
        expect(toggleGlyph()).toBe(moon);
        light.unmount();

        renderShell("/welcome", { theme: "dark" });
        expect(toggleGlyph()).toBe(sun);
    });

    it("calls back to the host when the theme toggle is pressed", async () => {
        const onToggleTheme = vi.fn();
        const { user } = renderShell("/welcome", { onToggleTheme });
        await user.click(screen.getByLabelText("Toggle theme"));
        expect(onToggleTheme).toHaveBeenCalledOnce();
    });

    it("carries the burger and the doc sidebar only on documentation routes", () => {
        const landing = renderShell("/welcome");
        expect(screen.queryByLabelText("Toggle navigation")).not.toBeInTheDocument();
        expect(landing.container.querySelector<HTMLElement>(".docs-side")!).not.toBeInTheDocument();
        landing.unmount();

        const { container } = renderShell("/docs/getting-started");
        expect(screen.getByLabelText("Toggle navigation")).toBeInTheDocument();
        expect(container.querySelector<HTMLElement>(".docs-side")!).toBeInTheDocument();
    });

    it("opens the mobile menu with the burger and closes it again on the next press", async () => {
        const { user, container } = renderShell("/docs/getting-started");
        const sidebar = container.querySelector<HTMLElement>(".docs-side")!;
        expect(sidebar).not.toHaveClass("docs-side_open");

        await user.click(screen.getByLabelText("Toggle navigation"));
        await waitFor(() => expect(sidebar).toHaveClass("docs-side_open"));

        await user.click(screen.getByLabelText("Toggle navigation"));
        await waitFor(() => expect(sidebar).not.toHaveClass("docs-side_open"));
    });

    it("closes the mobile menu once a doc page is picked from it", async () => {
        const { user, container } = renderShell("/docs/getting-started");
        const sidebar = container.querySelector<HTMLElement>(".docs-side")!;
        await user.click(screen.getByLabelText("Toggle navigation"));
        await waitFor(() => expect(sidebar).toHaveClass("docs-side_open"));

        await user.click(screen.getByRole("link", { name: "Budgeting" }));
        await waitFor(() => expect(sidebar).not.toHaveClass("docs-side_open"));
    });

    it("marks the sidebar link of the page being read", () => {
        renderShell("/docs/budgeting");
        expect(screen.getByRole("link", { name: "Budgeting" })).toHaveClass(
            "docs-side__link_active",
        );
        expect(screen.getByRole("link", { name: "Transactions" })).not.toHaveClass(
            "docs-side__link_active",
        );
    });
});
