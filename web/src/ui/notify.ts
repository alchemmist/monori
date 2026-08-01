import { notifications } from "@mantine/notifications";
import type { ToastMessage } from "../types.js";

const COLORS = {
    danger: "red",
    success: "teal",
    warning: "yellow",
    info: "blue",
};

/* Store toasts keep the gravity shape ({ title, content, theme }) so call
 * sites didn't have to change; this maps them onto Mantine notifications. */
export function showToast({ title, content, theme }: ToastMessage) {
    notifications.show({
        title,
        message: content ?? "",
        color: theme && theme in COLORS ? COLORS[theme as keyof typeof COLORS] : "gray",
        autoClose: 5000,
    });
}
