import { notifications } from "@mantine/notifications";

const COLORS = {
    danger: "red",
    success: "teal",
    warning: "yellow",
    info: "blue",
};

/* Store toasts keep the gravity shape ({ title, content, theme }) so call
 * sites didn't have to change; this maps them onto Mantine notifications. */
export function showToast({ title, content, theme }) {
    notifications.show({
        title,
        message: content ?? "",
        color: COLORS[theme] ?? "gray",
        autoClose: 5000,
    });
}
