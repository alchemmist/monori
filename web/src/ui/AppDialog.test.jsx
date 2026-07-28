import { describe, expect, it, vi } from "vitest";
import AppDialog from "./AppDialog.jsx";
import { renderUI, screen } from "../test/render.jsx";

/** Mantine turns a px modal size into this scale-aware rem custom property. */
const rem = (px) => `calc(${px / 16}rem * var(--mantine-scale))`;

/** Render a dialog on its own and read back the width it asked Mantine for. */
function modalSize(ui) {
    const { unmount } = renderUI(ui);
    const value = document
        .querySelector(".mantine-Modal-root")
        .style.getPropertyValue("--modal-size");
    unmount();
    return value;
}

describe("AppDialog", () => {
    it("shows the title and body content", () => {
        const onClose = vi.fn();
        renderUI(
            <AppDialog title="Edit account" onClose={onClose}>
                <p>body</p>
            </AppDialog>,
        );
        expect(screen.getByText("Edit account")).toBeInTheDocument();
        expect(screen.getByText("body")).toBeInTheDocument();
    });

    it("renders no footer at all without applyText", () => {
        renderUI(<AppDialog title="Plain" onClose={() => {}} />);
        expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    });

    it("applies and cancels through the footer buttons", async () => {
        const onApply = vi.fn();
        const onClose = vi.fn();
        const { user } = renderUI(
            <AppDialog title="T" onClose={onClose} applyText="Save" onApply={onApply} />,
        );
        await user.click(screen.getByRole("button", { name: "Save" }));
        expect(onApply).toHaveBeenCalled();
        await user.click(screen.getByRole("button", { name: "Cancel" }));
        expect(onClose).toHaveBeenCalled();
    });

    it("prefers an explicit onCancel over onClose, and uses the given cancel label", async () => {
        const onCancel = vi.fn();
        const onClose = vi.fn();
        const { user } = renderUI(
            <AppDialog
                title="T"
                onClose={onClose}
                onCancel={onCancel}
                cancelText="Back"
                applyText="Go"
            />,
        );
        await user.click(screen.getByRole("button", { name: "Back" }));
        expect(onCancel).toHaveBeenCalled();
        expect(onClose).not.toHaveBeenCalled();
    });

    it("disables the apply button, so a click does nothing", async () => {
        const onApply = vi.fn();
        const { user } = renderUI(
            <AppDialog
                title="T"
                onClose={() => {}}
                applyText="Save"
                onApply={onApply}
                applyDisabled
            />,
        );
        const apply = screen.getByRole("button", { name: "Save" });
        expect(apply).toBeDisabled();
        await user.click(apply);
        expect(onApply).not.toHaveBeenCalled();
    });

    // a destructive apply is outlined, not filled: the solid brand button is
    // reserved for the safe action, so an inverted pair would invite the delete
    it("marks a destructive apply with the danger tone and an outline button", () => {
        renderUI(
            <AppDialog
                title="T"
                onClose={() => {}}
                applyText="Delete"
                onApply={() => {}}
                applyDanger
            />,
        );
        const apply = screen.getByRole("button", { name: "Delete" });
        expect(apply).toHaveAttribute("data-tone", "danger");
        expect(apply).toHaveAttribute("data-variant", "outline");
    });

    it("carries no danger tone and a filled button by default", () => {
        renderUI(<AppDialog title="T" onClose={() => {}} applyText="Save" onApply={() => {}} />);
        const apply = screen.getByRole("button", { name: "Save" });
        expect(apply).not.toHaveAttribute("data-tone");
        expect(apply).toHaveAttribute("data-variant", "filled");
    });

    it("keeps cancel visually subordinate to whichever apply is shown", () => {
        const { unmount } = renderUI(
            <AppDialog title="T" onClose={() => {}} applyText="Save" onApply={() => {}} />,
        );
        expect(screen.getByRole("button", { name: "Cancel" })).toHaveAttribute(
            "data-variant",
            "subtle",
        );
        unmount();
        renderUI(
            <AppDialog
                title="T"
                onClose={() => {}}
                applyText="Delete"
                onApply={() => {}}
                applyDanger
            />,
        );
        expect(screen.getByRole("button", { name: "Cancel" })).toHaveAttribute(
            "data-variant",
            "subtle",
        );
    });

    it("shows a loader on the apply button while the action runs", () => {
        renderUI(
            <AppDialog
                title="T"
                onClose={() => {}}
                applyText="Save"
                onApply={() => {}}
                applyLoading
            />,
        );
        expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("data-loading");
    });

    it("widens for the large size and takes a raw size through untouched", () => {
        // 480 and 900px, expressed by Mantine as scale-aware rem
        expect(modalSize(<AppDialog title="Small" onClose={() => {}} />)).toBe(rem(480));
        expect(modalSize(<AppDialog title="Big" size="l" onClose={() => {}} />)).toBe(rem(900));
        // large really is the wider of the two, whichever way the map is read
        expect(modalSize(<AppDialog title="Big" size="l" onClose={() => {}} />)).not.toBe(
            modalSize(<AppDialog title="Small" size="s" onClose={() => {}} />),
        );
        // an unknown size is not looked up at all, it is handed to Mantine as-is
        expect(modalSize(<AppDialog title="Raw" size="720px" onClose={() => {}} />)).toBe(rem(720));
    });
});
