import { createTheme } from "@mantine/core";

/* Mantine carries behavior only; the Mono look (colors, metrics) is applied in
 * ui/mantine.css via the --m-* tokens so both themes flip with the body class. */
export const theme = createTheme({
    // theme.css sets html font-size to 14px; counter-scale so Mantine's
    // rem-based metrics still resolve to their intended px values
    scale: 16 / 14,
    fontFamily: "'Inter Variable', var(--g-font-family-sans, sans-serif)",
    defaultRadius: "6px",
    cursorType: "pointer",
    components: {
        Button: { defaultProps: { size: "m" } },
        Select: {
            defaultProps: {
                allowDeselect: false,
                checkIconPosition: "right",
                comboboxProps: { shadow: "md", offset: 4 },
                withScrollArea: false,
            },
        },
        Menu: { defaultProps: { shadow: "md", position: "bottom", offset: 4 } },
        Modal: {
            defaultProps: {
                centered: true,
                overlayProps: { backgroundOpacity: 0.5 },
                transitionProps: { duration: 100 },
            },
        },
        Tooltip: { defaultProps: { withArrow: false } },
    },
});
