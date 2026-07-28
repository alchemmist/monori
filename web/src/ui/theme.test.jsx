import { describe, expect, it } from "vitest";
import { Button, MantineProvider, Menu, Modal, Select, Tooltip } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { theme } from "./theme.js";

const wrap = (ui) =>
    render(
        <MantineProvider theme={theme} forceColorScheme="light" env="test">
            {ui}
        </MantineProvider>,
    );

/** The same tree without the app theme, to prove a default really changed something. */
const bare = (ui) =>
    render(
        <MantineProvider forceColorScheme="light" env="test">
            {ui}
        </MantineProvider>,
    );

describe("theme", () => {
    // theme.css sets html to 14px; without the counter-scale every Mantine
    // metric would render at 14/16 of its intended size
    it("counter-scales the 14px root font so Mantine rems land on their px values", () => {
        wrap(<div />);
        const scale = document.querySelector("style[data-mantine-styles]")?.textContent ?? "";
        expect(scale).toContain(`--mantine-scale: ${16 / 14}`);
    });

    it("rounds every surface to the app's own radius rather than Mantine's", () => {
        wrap(<div />);
        const styles = document.querySelector("style[data-mantine-styles]").textContent;
        // 6px, expressed by Mantine as a scale-aware rem
        expect(styles).toContain("--mantine-radius-default: calc(0.375rem * var(--mantine-scale))");
    });

    it("gives the whole app a pointer cursor on interactive controls", () => {
        wrap(<div />);
        expect(document.querySelector("style[data-mantine-styles]").textContent).toContain(
            "--mantine-cursor-type: pointer",
        );
    });

    // rows and toolbars are laid out around the medium button; Mantine's own
    // default is a size larger and would break every one of them
    it("gives buttons the app's size instead of Mantine's default", () => {
        wrap(<Button>Go</Button>);
        const themed = screen.getByRole("button", { name: "Go" });
        expect(themed.style.getPropertyValue("--button-height")).toBe("var(--button-height-m)");
        expect(themed.style.getPropertyValue("--button-fz")).toBe("var(--mantine-font-size-m)");

        bare(<Button>Plain</Button>);
        const plain = screen.getByRole("button", { name: "Plain" });
        expect(plain.style.getPropertyValue("--button-height")).not.toBe(
            themed.style.getPropertyValue("--button-height"),
        );
    });

    // a select that clears itself when the chosen option is picked again loses
    // the value silently, and the tick belongs after the label, not before it
    it("keeps a select from deselecting and puts the check on the right", async () => {
        const user = userEvent.setup({ delay: null });
        wrap(<Select data={["One", "Two"]} label="Pick" defaultValue="One" />);
        const input = screen.getByRole("combobox", { name: "Pick" });
        await user.click(input);

        const chosen = await waitFor(() => {
            const el = document.querySelector('[role="option"][value="One"]');
            expect(el).toBeInTheDocument();
            return el;
        });
        expect(chosen).toHaveAttribute("data-checked", "true");
        // Mantine flips the option's children to put the check last
        expect(chosen).toHaveAttribute("data-reverse", "true");

        await user.click(chosen);
        // re-picking the selected option keeps it, rather than clearing the field
        expect(input).toHaveValue("One");
    });

    it("renders the whole option list inline instead of inside a scroll area", async () => {
        const user = userEvent.setup({ delay: null });
        wrap(<Select data={["One", "Two"]} label="Pick" />);
        await user.click(screen.getByRole("combobox", { name: "Pick" }));
        await waitFor(() => expect(document.querySelectorAll('[role="option"]')).toHaveLength(2));
        expect(document.querySelector(".mantine-ScrollArea-root")).toBeNull();
    });

    it("centres modals and dims the page behind them", () => {
        wrap(<Modal opened onClose={() => {}} title="Hi" />);
        expect(screen.getByText("Hi")).toBeInTheDocument();
        expect(document.querySelector(".mantine-Modal-root")).toHaveAttribute(
            "data-centered",
            "true",
        );
        expect(
            document.querySelector(".mantine-Modal-overlay").style.getPropertyValue("--overlay-bg"),
        ).toBe("rgba(0, 0, 0, 0.5)");
    });

    it("anchors menus below their target with a shadow", async () => {
        const user = userEvent.setup({ delay: null });
        wrap(
            <Menu>
                <Menu.Target>
                    <button type="button">Open</button>
                </Menu.Target>
                <Menu.Dropdown>
                    <Menu.Item>Item</Menu.Item>
                </Menu.Dropdown>
            </Menu>,
        );
        await user.click(screen.getByRole("button", { name: "Open" }));
        const dropdown = await waitFor(() => {
            const el = document.querySelector('[role="menu"]');
            expect(el).toBeInTheDocument();
            return el;
        });
        expect(dropdown).toHaveAttribute("data-position", "bottom");
        expect(dropdown.style.getPropertyValue("--popover-shadow")).toBe(
            "var(--mantine-shadow-md)",
        );
    });

    it("drops the tooltip arrow", async () => {
        const user = userEvent.setup({ delay: null });
        wrap(
            <Tooltip label="Hint">
                <button type="button">Hover</button>
            </Tooltip>,
        );
        await user.hover(screen.getByRole("button", { name: "Hover" }));
        await waitFor(() => expect(screen.getByText("Hint")).toBeInTheDocument());
        expect(document.querySelector(".mantine-Tooltip-arrow")).toBeNull();
    });
});
