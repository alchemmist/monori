import { Button, Modal } from "@mantine/core";

const WIDTHS = { s: 480, l: 900 };

/* Shared dialog frame: Mantine Modal + the standard footer every dialog here
 * uses (flat cancel on the left of a filled/danger apply). */
export default function AppDialog({
    title,
    onClose,
    size = "s",
    children,
    applyText,
    onApply,
    applyLoading = false,
    applyDisabled = false,
    applyDanger = false,
    cancelText = "Cancel",
    onCancel,
}) {
    return (
        <Modal opened onClose={onClose} title={title} size={WIDTHS[size] ?? size}>
            {children}
            {applyText && (
                <div className="app-dialog__footer">
                    <Button size="l" variant="subtle" onClick={onCancel ?? onClose}>
                        {cancelText}
                    </Button>
                    <Button
                        size="l"
                        variant={applyDanger ? "outline" : "filled"}
                        data-tone={applyDanger ? "danger" : undefined}
                        loading={applyLoading}
                        disabled={applyDisabled}
                        onClick={onApply}
                    >
                        {applyText}
                    </Button>
                </div>
            )}
        </Modal>
    );
}
