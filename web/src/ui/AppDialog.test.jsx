import { describe, expect, it, vi } from "vitest";
import AppDialog from "./AppDialog.jsx";
import { renderUI, screen } from "../test/render.jsx";

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

    it("marks a destructive apply with the danger tone", () => {
        renderUI(
            <AppDialog
                title="T"
                onClose={() => {}}
                applyText="Delete"
                onApply={() => {}}
                applyDanger
            />,
        );
        expect(screen.getByRole("button", { name: "Delete" })).toHaveAttribute(
            "data-tone",
            "danger",
        );
    });

    it("carries no danger tone by default", () => {
        renderUI(<AppDialog title="T" onClose={() => {}} applyText="Save" onApply={() => {}} />);
        expect(screen.getByRole("button", { name: "Save" })).not.toHaveAttribute("data-tone");
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
        const { unmount } = renderUI(
            <AppDialog title="Big" size="l" onClose={() => {}}>
                <p>wide</p>
            </AppDialog>,
        );
        expect(screen.getByText("wide")).toBeInTheDocument();
        unmount();
        renderUI(
            <AppDialog title="Raw" size="720px" onClose={() => {}}>
                <p>raw</p>
            </AppDialog>,
        );
        expect(screen.getByText("raw")).toBeInTheDocument();
    });
});
