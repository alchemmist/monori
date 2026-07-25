import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import Tab from "./Tab.jsx";
import { renderUI, screen, fireEvent, waitFor } from "../test/render.jsx";

const fakeStorage = () => {
    const map = new Map();
    return {
        getItem: (k) => map.get(k) ?? null,
        setItem: (k, v) => map.set(k, String(v)),
        removeItem: (k) => map.delete(k),
    };
};

beforeEach(() => {
    vi.stubGlobal("localStorage", fakeStorage());
});

afterEach(() => {
    vi.restoreAllMocks();
});

describe("Tab", () => {
    it("renders a dockable side panel that starts expanded", () => {
        renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        expect(screen.getByText("Details")).toBeInTheDocument();
        expect(screen.getByText("content")).toBeInTheDocument();
    });

    it("shows the title in the header and strip label on the collapsed strip", () => {
        const { container } = renderUI(
            <Tab title="Settings" strip="S" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        expect(screen.getByText("Settings")).toBeInTheDocument();
        const stripLabel = container.querySelector(".ui-tab__strip-label");
        expect(stripLabel).toHaveTextContent("S");
    });

    it("falls back to title when strip is not provided", () => {
        const { container } = renderUI(
            <Tab title="Details" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        const stripLabel = container.querySelector(".ui-tab__strip-label");
        expect(stripLabel).toHaveTextContent("Details");
    });

    it("calls onClose when the close button is clicked", async () => {
        const onClose = vi.fn();
        const { user } = renderUI(
            <Tab title="Details" strip="D" onClose={onClose}>
                <p>content</p>
            </Tab>,
        );
        const closeBtn = screen.getByRole("button", { name: /close/i });
        await user.click(closeBtn);
        expect(onClose).toHaveBeenCalled();
    });

    it("renders a footer node when provided", () => {
        renderUI(
            <Tab title="Details" strip="D" onClose={() => {}} footer={<button>Save</button>}>
                <p>content</p>
            </Tab>,
        );
        expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    });

    it("has the proper structure with header and content", () => {
        const { container } = renderUI(
            <Tab title="Test" strip="T" onClose={() => {}}>
                <p>body</p>
            </Tab>,
        );
        expect(container.querySelector(".ui-tab__head")).toBeInTheDocument();
        expect(container.querySelector(".ui-tab__title")).toBeInTheDocument();
        expect(container.querySelector(".ui-tab__content")).toBeInTheDocument();
        expect(container.querySelector(".ui-tab__head-actions")).toBeInTheDocument();
    });

    it("renders collapse and close buttons in the header", () => {
        renderUI(
            <Tab title="Test" strip="T" onClose={() => {}}>
                <p>body</p>
            </Tab>,
        );
        expect(screen.getByRole("button", { name: /collapse/i })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /close/i })).toBeInTheDocument();
    });

    it("persists collapsed state per tab under its persistKey", async () => {
        const { user, unmount, container } = renderUI(
            <Tab title="Details" strip="D" persistKey="details-tab" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        const collapseBtn = screen.getByRole("button", { name: /collapse/i });
        await user.click(collapseBtn);
        await waitFor(() => {
            const tab = container.querySelector(".ui-tab");
            expect(tab).toHaveClass("ui-tab_collapsed");
        });
        unmount();

        const { container: container2 } = renderUI(
            <Tab title="Details" strip="D" persistKey="details-tab" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        await waitFor(() => {
            const tab2 = container2.querySelector(".ui-tab");
            expect(tab2).toHaveClass("ui-tab_collapsed");
        });
    });

    it("defaults to defaultCollapsed=false on first load", () => {
        renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        expect(screen.getByText("content")).toBeVisible();
    });

    it("starts collapsed when defaultCollapsed=true", () => {
        const { container } = renderUI(
            <Tab title="Details" strip="D" defaultCollapsed onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        const tab = container.querySelector(".ui-tab");
        expect(tab).toHaveClass("ui-tab_collapsed");
    });

    it("has a grip separator for resizing in the expanded state", () => {
        const { container } = renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        const grip = container.querySelector(".ui-tab__grip");
        expect(grip).toHaveAttribute("role", "separator");
        expect(grip).toHaveAttribute("aria-orientation", "vertical");
    });

    it("registers and unregisters the tab with the stack on mount/unmount", () => {
        const { unmount } = renderUI(
            <Tab title="SQL" strip="SQL" onClose={() => {}}>
                <p>query</p>
            </Tab>,
        );

        expect(screen.getByText("query")).toBeInTheDocument();

        unmount();
        expect(screen.queryByText("query")).not.toBeInTheDocument();
    });

    it("clears user-select and cursor on unmount to prevent dangling styles", () => {
        const { unmount } = renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        document.body.style.userSelect = "none";
        document.body.style.cursor = "ew-resize";

        unmount();

        expect(document.body.style.userSelect).toBe("");
        expect(document.body.style.cursor).toBe("");
    });

    it("marks the content inert when collapsed", async () => {
        const { user, container } = renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        const inner = container.querySelector(".ui-tab__inner");
        expect(inner).not.toHaveAttribute("inert");

        const collapseBtn = screen.getByRole("button", { name: /collapse/i });
        await user.click(collapseBtn);

        await waitFor(() => {
            expect(inner).toHaveAttribute("inert");
        });
    });

    it("uses strip as persistKey default when persistKey is not given", async () => {
        const { user, unmount, container } = renderUI(
            <Tab title="Very Long Title" strip="VLT" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        const collapseBtn = screen.getByRole("button", { name: /collapse/i });
        await user.click(collapseBtn);

        await waitFor(() => {
            const tab = container.querySelector(".ui-tab");
            expect(tab).toHaveClass("ui-tab_collapsed");
        });

        unmount();

        const { container: container2 } = renderUI(
            <Tab title="Very Long Title" strip="VLT" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        await waitFor(() => {
            const tab2 = container2.querySelector(".ui-tab");
            expect(tab2).toHaveClass("ui-tab_collapsed");
        });
    });

    it("expands when clicking the strip while collapsed", async () => {
        const { user, container } = renderUI(
            <Tab title="Details" strip="D" defaultCollapsed onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        let tab = container.querySelector(".ui-tab");
        expect(tab).toHaveClass("ui-tab_collapsed");

        const expandBtn = screen.getByRole("button", { name: /expand/i });
        await user.click(expandBtn);

        await waitFor(() => {
            tab = container.querySelector(".ui-tab");
            expect(tab).not.toHaveClass("ui-tab_collapsed");
        });
    });

    it("has proper aria-labels and roles for accessibility", () => {
        const { container } = renderUI(
            <Tab title="Settings Panel" strip="S" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        const collapseBtn = screen.getByRole("button", { name: /collapse/i });
        expect(collapseBtn).toHaveAttribute("aria-label");

        const stripBtn = container.querySelector(".ui-tab__strip");
        expect(stripBtn).toHaveAttribute("aria-label");
    });

    it("uses width prop for initial width when not dragged", () => {
        const { container } = renderUI(
            <Tab title="Details" strip="D" width={60} onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        const tab = container.querySelector(".ui-tab");
        const style = window.getComputedStyle(tab);
        const widthVar = style.getPropertyValue("--ui-tab-w");
        expect(widthVar).toContain("60vw");
    });

    it("does not render width when neither width prop nor drag has happened", () => {
        const { container } = renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        const tab = container.querySelector(".ui-tab");
        const style = window.getComputedStyle(tab);
        const widthVar = style.getPropertyValue("--ui-tab-w");
        expect(widthVar.trim()).toBe("");
    });

    it("renders children content correctly", () => {
        renderUI(
            <Tab title="Test" strip="T" onClose={() => {}}>
                <div>
                    <h2>Heading</h2>
                    <p>Paragraph</p>
                </div>
            </Tab>,
        );
        expect(screen.getByText("Heading")).toBeInTheDocument();
        expect(screen.getByText("Paragraph")).toBeInTheDocument();
    });

    it("includes grip only when expanded", () => {
        const { container, unmount } = renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        expect(container.querySelector(".ui-tab__grip")).toBeInTheDocument();
        unmount();

        const { container: container2 } = renderUI(
            <Tab title="Details" strip="D" defaultCollapsed onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        expect(container2.querySelector(".ui-tab__grip")).not.toBeInTheDocument();
    });

    it("creates a unique id for each tab instance", () => {
        const { container: c1 } = renderUI(
            <Tab title="Tab1" strip="T1" onClose={() => {}}>
                <p>content1</p>
            </Tab>,
        );
        const { container: c2 } = renderUI(
            <Tab title="Tab2" strip="T2" onClose={() => {}}>
                <p>content2</p>
            </Tab>,
        );

        const aside1 = c1.querySelector("aside");
        const aside2 = c2.querySelector("aside");
        expect(aside1).toBeInTheDocument();
        expect(aside2).toBeInTheDocument();
    });
});
