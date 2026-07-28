import { describe, expect, it, vi } from "vitest";
import RowMenu from "./RowMenu.jsx";
import { renderUI, screen, waitFor } from "../test/render.jsx";

/** Mantine renders the icon-button's px size into this custom property as rem. */
const sizeVar = (button) => button.style.getPropertyValue("--ai-size");

/** Open the menu and hand back its dropdown element. */
async function open(user) {
    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(document.querySelector('[role="menu"]')).toBeInTheDocument());
    return document.querySelector('[role="menu"]');
}

describe("RowMenu", () => {
    it("renders a button with default aria-label", () => {
        renderUI(<RowMenu items={[{ text: "Edit", action: () => {} }]} />);
        expect(screen.getByRole("button", { name: "Actions" })).toBeInTheDocument();
    });

    it("renders menu items", async () => {
        const { user } = renderUI(
            <RowMenu
                items={[
                    { text: "Edit", action: () => {} },
                    { text: "Delete", action: () => {} },
                ]}
            />,
        );
        await user.click(screen.getByRole("button"));
        await waitFor(() => {
            expect(screen.getByRole("menuitem", { name: "Edit" })).toBeInTheDocument();
            expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
        });
    });

    it("calls action when menu item is clicked", async () => {
        const action = vi.fn();
        const { user } = renderUI(<RowMenu items={[{ text: "Copy", action }]} />);
        await user.click(screen.getByRole("button"));
        const copyItem = await screen.findByRole("menuitem", { name: "Copy" });
        await user.click(copyItem);
        expect(action).toHaveBeenCalled();
    });

    it("applies theme to menu items as data-tone attribute", async () => {
        const { user } = renderUI(
            <RowMenu
                items={[
                    { text: "Safe", action: () => {}, theme: "success" },
                    { text: "Dangerous", action: () => {}, theme: "danger" },
                ]}
            />,
        );
        await user.click(screen.getByRole("button"));
        await waitFor(() => {
            const safe = screen.getByRole("menuitem", { name: "Safe" });
            const dangerous = screen.getByRole("menuitem", { name: "Dangerous" });
            expect(safe).toHaveAttribute("data-tone", "success");
            expect(dangerous).toHaveAttribute("data-tone", "danger");
        });
    });

    // rows are dense, so the default has to be the 24px button — the 28px one
    // would push every row taller
    it("renders at 24px by default", () => {
        renderUI(<RowMenu items={[{ text: "Action", action: () => {} }]} />);
        expect(sizeVar(screen.getByRole("button"))).toBe("calc(1.5rem * var(--mantine-scale))");
    });

    it("maps each size alias onto its own pixel size", () => {
        const cases = [
            ["xs", "calc(1.25rem * var(--mantine-scale))"],
            ["s", "calc(1.5rem * var(--mantine-scale))"],
            ["m", "calc(1.75rem * var(--mantine-scale))"],
        ];
        const seen = new Set();
        for (const [size, expected] of cases) {
            const { unmount } = renderUI(
                <RowMenu size={size} items={[{ text: "Action", action: () => {} }]} />,
            );
            const actual = sizeVar(screen.getByRole("button"));
            expect(actual).toBe(expected);
            seen.add(actual);
            unmount();
        }
        // three aliases, three distinct sizes — no alias silently collapses
        expect(seen.size).toBe(3);
    });

    it("passes a non-alias size straight through to the button", () => {
        renderUI(<RowMenu size="32" items={[{ text: "Action", action: () => {} }]} />);
        expect(sizeVar(screen.getByRole("button"))).toBe("calc(2rem * var(--mantine-scale))");
    });

    it("applies custom className to the button", () => {
        renderUI(<RowMenu className="my-menu" items={[{ text: "Action", action: () => {} }]} />);
        expect(screen.getByRole("button")).toHaveClass("my-menu");
    });

    it("uses custom label for aria-label", () => {
        renderUI(<RowMenu label="More options" items={[{ text: "Action", action: () => {} }]} />);
        expect(screen.getByRole("button", { name: "More options" })).toBeInTheDocument();
    });

    it("swaps the ellipsis for a custom icon rather than showing both", () => {
        const { container } = renderUI(
            <RowMenu
                icon={<span data-testid="custom-icon">custom</span>}
                items={[{ text: "Action", action: () => {} }]}
            />,
        );
        expect(screen.getByTestId("custom-icon")).toBeInTheDocument();
        expect(container.querySelector("svg")).toBeNull();
    });

    it("falls back to the ellipsis icon when no icon is given", () => {
        const { container } = renderUI(<RowMenu items={[{ text: "Action", action: () => {} }]} />);
        expect(container.querySelectorAll("svg")).toHaveLength(1);
    });

    // a divider separates groups, so it belongs strictly *between* them: one
    // above the first group would leave a rule hanging under the dropdown edge
    it("puts a divider between groups and never before the first", async () => {
        const { user } = renderUI(
            <RowMenu
                items={[
                    [
                        { text: "Edit", action: () => {} },
                        { text: "Duplicate", action: () => {} },
                    ],
                    [{ text: "Archive", action: () => {} }],
                    [{ text: "Delete", action: () => {}, theme: "danger" }],
                ]}
            />,
        );
        const menu = await open(user);
        // three groups -> exactly two dividers
        expect(menu.querySelectorAll(".mantine-Menu-divider")).toHaveLength(2);

        // and they sit at the group seams, in reading order
        const rendered = [...menu.querySelectorAll('[role="menuitem"], .mantine-Menu-divider')].map(
            (el) => (el.getAttribute("role") === "menuitem" ? el.textContent : "---"),
        );
        expect(rendered).toEqual(["Edit", "Duplicate", "---", "Archive", "---", "Delete"]);
    });

    it("draws no divider for a flat list, however many items it holds", async () => {
        const { user } = renderUI(
            <RowMenu
                items={[
                    { text: "First", action: () => {} },
                    { text: "Second", action: () => {} },
                    { text: "Third", action: () => {} },
                ]}
            />,
        );
        const menu = await open(user);
        expect(menu.querySelectorAll(".mantine-Menu-divider")).toHaveLength(0);
        expect([...menu.querySelectorAll('[role="menuitem"]')].map((el) => el.textContent)).toEqual(
            ["First", "Second", "Third"],
        );
    });

    // the same two items flat vs. split in two must not render identically —
    // otherwise the grouping prop is doing nothing
    it("renders a grouped list differently from the same items flat", async () => {
        const items = [
            { text: "Edit", action: () => {} },
            { text: "Delete", action: () => {} },
        ];
        const flat = renderUI(<RowMenu items={items} />);
        const flatMenu = await open(flat.user);
        expect(flatMenu.querySelectorAll(".mantine-Menu-divider")).toHaveLength(0);
        flat.unmount();

        const grouped = renderUI(<RowMenu items={[[items[0]], [items[1]]]} />);
        const groupedMenu = await open(grouped.user);
        expect(groupedMenu.querySelectorAll(".mantine-Menu-divider")).toHaveLength(1);
        // same items either way, only the separation differs
        expect(
            [...groupedMenu.querySelectorAll('[role="menuitem"]')].map((el) => el.textContent),
        ).toEqual(["Edit", "Delete"]);
    });

    it("renders menu items without theme attribute if not provided", async () => {
        const { user } = renderUI(<RowMenu items={[{ text: "Action", action: () => {} }]} />);
        await user.click(screen.getByRole("button"));
        const item = await screen.findByRole("menuitem");
        expect(item).not.toHaveAttribute("data-tone");
    });
});
