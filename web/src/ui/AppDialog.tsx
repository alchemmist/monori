import { Button, Modal } from "@mantine/core";
import type { ReactNode } from "react";

const WIDTHS = { s: 480, l: 900 };

interface AppDialogProps {
    title: ReactNode;
    onClose: () => void;
    size?: number | string;
    children?: ReactNode;
    applyText?: string;
    onApply?: () => void;
    applyLoading?: boolean;
    applyDisabled?: boolean;
    applyDanger?: boolean;
    cancelText?: string;
    onCancel?: () => void;
}

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
}: AppDialogProps) {
    return (
        <Modal
            opened
            onClose={onClose}
            title={title}
            size={size in WIDTHS ? WIDTHS[size as "s" | "l"] : size}
        >
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
