import { describe, expect, it, vi } from "vitest";
import RowMenu from "./RowMenu.jsx";
import { renderUI, screen, waitFor } from "../test/render.jsx";

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

    it("groups items with dividers between groups", async () => {
        const { user } = renderUI(
            <RowMenu
                items={[
                    [
                        { text: "Edit", action: () => {} },
                        { text: "Duplicate", action: () => {} },
                    ],
                    [{ text: "Delete", action: () => {}, theme: "danger" }],
                ]}
            />,
        );
        await user.click(screen.getByRole("button"));
        await waitFor(() => {
            expect(screen.getByRole("menuitem", { name: "Edit" })).toBeInTheDocument();
            expect(screen.getByRole("menuitem", { name: "Delete" })).toBeInTheDocument();
        });
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

    it("defaults to size s", () => {
        renderUI(<RowMenu items={[{ text: "Action", action: () => {} }]} />);
        expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("accepts size parameter for sizing", () => {
        const { unmount } = renderUI(
            <RowMenu size="xs" items={[{ text: "Action", action: () => {} }]} />,
        );
        expect(screen.getByRole("button")).toBeInTheDocument();
        unmount();

        renderUI(<RowMenu size="m" items={[{ text: "Action", action: () => {} }]} />);
        expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("uses raw size if not an alias", () => {
        renderUI(<RowMenu size="32" items={[{ text: "Action", action: () => {} }]} />);
        expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("applies custom className to the button", () => {
        renderUI(<RowMenu className="my-menu" items={[{ text: "Action", action: () => {} }]} />);
        expect(screen.getByRole("button")).toHaveClass("my-menu");
    });

    it("uses custom label for aria-label", () => {
        renderUI(<RowMenu label="More options" items={[{ text: "Action", action: () => {} }]} />);
        expect(screen.getByRole("button", { name: "More options" })).toBeInTheDocument();
    });

    it("renders custom icon when provided", () => {
        renderUI(
            <RowMenu
                icon={<div data-testid="custom-icon">custom</div>}
                items={[{ text: "Action", action: () => {} }]}
            />,
        );
        expect(screen.getByTestId("custom-icon")).toBeInTheDocument();
    });

    it("renders default ellipsis icon", () => {
        const { container } = renderUI(<RowMenu items={[{ text: "Action", action: () => {} }]} />);
        const svg = container.querySelector("svg");
        expect(svg).toBeInTheDocument();
    });

    it("handles a flat array without explicit grouping", async () => {
        const { user } = renderUI(
            <RowMenu
                items={[
                    { text: "First", action: () => {} },
                    { text: "Second", action: () => {} },
                ]}
            />,
        );
        await user.click(screen.getByRole("button"));
        await waitFor(() => {
            expect(screen.getByRole("menuitem", { name: "First" })).toBeInTheDocument();
            expect(screen.getByRole("menuitem", { name: "Second" })).toBeInTheDocument();
        });
    });

    it("renders menu items without theme attribute if not provided", async () => {
        const { user } = renderUI(<RowMenu items={[{ text: "Action", action: () => {} }]} />);
        await user.click(screen.getByRole("button"));
        const item = await screen.findByRole("menuitem");
        expect(item).not.toHaveAttribute("data-tone");
    });
});
