import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import Tab from "./Tab.jsx";
import { act, renderUI, screen, fireEvent, waitFor } from "../test/render.jsx";

const fakeStorage = () => {
    const map = new Map<string, string>();
    return {
        getItem: (key: string) => map.get(key) ?? null,
        setItem: (key: string, value: string) => map.set(key, String(value)),
        removeItem: (key: string) => map.delete(key),
    };
};

/** "420px" -> 420, so offsets can be compared as numbers. */
const px = (value: string) => Number.parseFloat(value);

// the jsdom stub in test/setup.js measures every element at 1200px wide, which
// is the width a tab registers with the stack and the width a drag starts from
const RENDERED_TAB_WIDTH = 1200;

/** The resize clamp is a share of the viewport, so pin it for the drag tests. */
const setViewportWidth = (value: number) =>
    Object.defineProperty(window, "innerWidth", { configurable: true, value });

beforeEach(() => {
    vi.stubGlobal("localStorage", fakeStorage());
    setViewportWidth(1000);
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
        const stripLabel = container.querySelector<HTMLElement>(".ui-tab__strip-label")!;
        expect(stripLabel).toHaveTextContent("S");
    });

    it("falls back to title when strip is not provided", () => {
        const { container } = renderUI(
            <Tab title="Details" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        const stripLabel = container.querySelector<HTMLElement>(".ui-tab__strip-label")!;
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
            const tab = container.querySelector<HTMLElement>(".ui-tab")!;
            expect(tab).toHaveClass("ui-tab_collapsed");
        });
        unmount();

        const { container: container2 } = renderUI(
            <Tab title="Details" strip="D" persistKey="details-tab" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        await waitFor(() => {
            const tab2 = container2.querySelector<HTMLElement>(".ui-tab")!;
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
        const tab = container.querySelector<HTMLElement>(".ui-tab")!;
        expect(tab).toHaveClass("ui-tab_collapsed");
    });

    it("has a grip separator for resizing in the expanded state", () => {
        const { container } = renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        const grip = container.querySelector<HTMLElement>(".ui-tab__grip")!;
        expect(grip).toHaveAttribute("role", "separator");
        expect(grip).toHaveAttribute("aria-orientation", "vertical");
    });

    // two tabs open at once must not overlap: the second is pushed left by the
    // first tab's width, and closing the first pulls it back to the edge
    it("takes a slot in the shared stack and gives it back on unmount", () => {
        const { container: first, unmount: closeFirst } = renderUI(
            <Tab title="First" strip="F" onClose={() => {}}>
                <p>one</p>
            </Tab>,
        );
        const base = px(first.querySelector<HTMLElement>("aside")!.style.right);

        const { container: second } = renderUI(
            <Tab title="Second" strip="S" onClose={() => {}}>
                <p>two</p>
            </Tab>,
        );
        const later = second.querySelector<HTMLElement>("aside")!;
        expect(px(later.style.right)).toBe(base + RENDERED_TAB_WIDTH);

        closeFirst();
        expect(px(later.style.right)).toBe(base);
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

        const inner = container.querySelector<HTMLElement>(".ui-tab__inner")!;
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
            const tab = container.querySelector<HTMLElement>(".ui-tab")!;
            expect(tab).toHaveClass("ui-tab_collapsed");
        });

        unmount();

        const { container: container2 } = renderUI(
            <Tab title="Very Long Title" strip="VLT" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        await waitFor(() => {
            const tab2 = container2.querySelector<HTMLElement>(".ui-tab")!;
            expect(tab2).toHaveClass("ui-tab_collapsed");
        });
    });

    it("expands when clicking the strip while collapsed", async () => {
        const { user, container } = renderUI(
            <Tab title="Details" strip="D" defaultCollapsed onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        let tab = container.querySelector<HTMLElement>(".ui-tab")!;
        expect(tab).toHaveClass("ui-tab_collapsed");

        const expandBtn = screen.getByRole("button", { name: /expand/i });
        await user.click(expandBtn);

        await waitFor(() => {
            tab = container.querySelector<HTMLElement>(".ui-tab")!;
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

        const stripBtn = container.querySelector<HTMLElement>(".ui-tab__strip")!;
        expect(stripBtn).toHaveAttribute("aria-label");
    });

    it("uses width prop for initial width when not dragged", () => {
        const { container } = renderUI(
            <Tab title="Details" strip="D" width={60} onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );

        const tab = container.querySelector<HTMLElement>(".ui-tab")!;
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

        const tab = container.querySelector<HTMLElement>(".ui-tab")!;
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
        expect(container.querySelector<HTMLElement>(".ui-tab__grip")!).toBeInTheDocument();
        unmount();

        const { container: container2 } = renderUI(
            <Tab title="Details" strip="D" defaultCollapsed onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        expect(container2.querySelector<HTMLElement>(".ui-tab__grip")!).not.toBeInTheDocument();
    });

    // the stack keys tabs by id, so two tabs sharing one would fight over the
    // same slot — visible as both landing on the same right offset
    it("gives each tab instance its own stack slot", () => {
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

        const right1 = px(c1.querySelector<HTMLElement>("aside")!.style.right);
        const right2 = px(c2.querySelector<HTMLElement>("aside")!.style.right);
        expect(right2).toBe(right1 + RENDERED_TAB_WIDTH);
        expect(right1).not.toBe(right2);
    });

    // dragging is what the user just did; a `width` prop is only the default the
    // call site asked for, so the drag has to win — otherwise the tab snaps back
    it("lets a dragged width override the declared width prop", () => {
        const { container } = renderUI(
            <Tab title="SQL" strip="SQL" width={60} persistKey="prec" onClose={() => {}}>
                content
            </Tab>,
        );
        const tab = container.querySelector<HTMLElement>(".ui-tab")!;
        expect(tab.style.getPropertyValue("--ui-tab-w")).toBe("60vw");

        const grip = container.querySelector<HTMLElement>(".ui-tab__grip")!;
        // the tab measures 1200px in jsdom; pushing the grip 600px right
        // narrows it to 600, inside the 100..900 clamp for a 1000px viewport
        fireEvent.pointerDown(grip, { pointerId: 1, clientX: 200 });
        fireEvent.pointerMove(window, { clientX: 800 });
        fireEvent.pointerUp(window, { clientX: 800 });
        expect(tab.style.getPropertyValue("--ui-tab-w")).toBe("600px");

        // and resetting the drag hands the prop back its say
        fireEvent.doubleClick(grip);
        expect(tab.style.getPropertyValue("--ui-tab-w")).toBe("60vw");
    });

    it("restores a remembered drag over the width prop on the next mount", () => {
        localStorage.setItem("monori_tab_width", JSON.stringify({ saved: 640 }));
        const { container } = renderUI(
            <Tab title="SQL" strip="SQL" width={60} persistKey="saved" onClose={() => {}}>
                content
            </Tab>,
        );
        expect(
            container.querySelector<HTMLElement>(".ui-tab")!.style.getPropertyValue("--ui-tab-w"),
        ).toBe("640px");
    });

    // the strip is the collapsed tab's only affordance; while the tab is open it
    // is decorative, so it must be out of the tab order and hidden from AT
    it("moves the strip in and out of the tab order with the collapse state", async () => {
        const { user, container } = renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                <p>content</p>
            </Tab>,
        );
        const strip = container.querySelector<HTMLElement>(".ui-tab__strip")!;
        expect(strip).toHaveAttribute("tabindex", "-1");
        expect(strip).toHaveAttribute("aria-hidden", "true");

        await user.click(screen.getByRole("button", { name: /collapse/i }));

        await waitFor(() => expect(strip).toHaveAttribute("tabindex", "0"));
        expect(strip).toHaveAttribute("aria-hidden", "false");
    });

    // a collapsed tab offers no resize at all: the grip is gone, so no pointer
    // gesture anywhere on it can start a drag or leave the page unselectable
    it("offers no resize handle at all while collapsed", async () => {
        const { user, container } = renderUI(
            <Tab title="Details" strip="D" defaultCollapsed onClose={() => {}}>
                content
            </Tab>,
        );
        const tab = container.querySelector<HTMLElement>(".ui-tab")!;
        expect(container.querySelector<HTMLElement>(".ui-tab__grip")!).not.toBeInTheDocument();

        fireEvent.pointerDown(tab, { pointerId: 1, clientX: 800 });
        fireEvent.pointerMove(window, { clientX: 100 });
        expect(document.body.style.userSelect).toBe("");
        expect(document.body.style.cursor).toBe("");
        expect(tab.style.getPropertyValue("--ui-tab-w")).toBe("");

        // expanding brings the handle back, and it works
        await user.click(screen.getByRole("button", { name: /expand/i }));
        const grip = await waitFor(() => {
            const el = container.querySelector<HTMLElement>(".ui-tab__grip")!;
            expect(el).toBeInTheDocument();
            return el;
        });
        fireEvent.pointerDown(grip, { pointerId: 1, clientX: 200 });
        expect(document.body.style.userSelect).toBe("none");
        fireEvent.pointerUp(window, { clientX: 200 });
    });

    // transitionend can be missed entirely (reduced motion, an interrupted
    // transition), so the gate has to lift on its own well inside a second
    it("lifts the input gate on a failsafe timer when no transition ever ends", async () => {
        vi.useFakeTimers();
        try {
            const { container } = renderUI(
                <Tab title="Details" strip="D" onClose={() => {}}>
                    content
                </Tab>,
            );
            const tab = container.querySelector<HTMLElement>(".ui-tab")!;
            fireEvent.click(screen.getByRole("button", { name: /collapse/i }));
            expect(tab).toHaveClass("ui-tab_animating");

            void act(() => vi.advanceTimersByTime(399));
            expect(tab).toHaveClass("ui-tab_animating");

            void act(() => vi.advanceTimersByTime(1));
            expect(tab).not.toHaveClass("ui-tab_animating");
        } finally {
            vi.useRealTimers();
        }
    });

    it("ends its input gate on the relevant width transition", async () => {
        const { user, container } = renderUI(
            <Tab title="Details" strip="D" onClose={() => {}}>
                content
            </Tab>,
        );
        const tab = container.querySelector<HTMLElement>(".ui-tab")!;
        await user.click(screen.getByRole("button", { name: /collapse/i }));
        expect(tab).toHaveClass("ui-tab_animating");
        fireEvent.transitionEnd(tab, { propertyName: "opacity" });
        expect(tab).toHaveClass("ui-tab_animating");
        fireEvent.transitionEnd(tab, { propertyName: "width" });
        expect(tab).not.toHaveClass("ui-tab_animating");
    });

    it("resizes within viewport bounds, persists the width, and resets it", () => {
        const { container } = renderUI(
            <Tab title="Details" strip="D" persistKey="resize" onClose={() => {}}>
                content
            </Tab>,
        );
        const tab = container.querySelector<HTMLElement>(".ui-tab")!;
        const grip = container.querySelector<HTMLElement>(".ui-tab__grip")!;
        fireEvent.pointerDown(grip, { pointerId: 1, clientX: 800 });
        expect(document.body.style.userSelect).toBe("none");
        fireEvent.pointerMove(window, { clientX: -1000 });
        expect(tab.style.getPropertyValue("--ui-tab-w")).toBe("900px");
        fireEvent.pointerUp(window, { clientX: -1000 });
        expect(document.body.style.userSelect).toBe("");
        expect(localStorage.getItem("monori_tab_width")).toBe('{"resize":900}');
        fireEvent.doubleClick(grip);
        expect(localStorage.getItem("monori_tab_width")).toBe("{}");
    });
});
