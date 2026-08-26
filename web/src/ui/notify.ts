import { notifications } from "@mantine/notifications";
import type { ToastMessage } from "../types.js";

const COLORS = {
    danger: "var(--m-expense)",
    success: "var(--m-income)",
    warning: "var(--m-warning)",
    info: "var(--m-chart-2)",
};
type ToastTheme = keyof typeof COLORS;

const isToastTheme = (theme: string): theme is ToastTheme => Object.hasOwn(COLORS, theme);

/* Store toasts keep the gravity shape ({ title, content, theme }) so call
 * sites didn't have to change; this maps them onto Mantine notifications. */
export function showToast({ title, content, theme }: ToastMessage) {
    notifications.show({
        title,
        message: content ?? "",
        color: theme != null && theme !== "" && isToastTheme(theme) ? COLORS[theme] : "gray",
        autoClose: 5000,
    });
}
