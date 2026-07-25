import { describe, expect, it } from "vitest";
import { Button, MantineProvider, Modal } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { theme } from "./theme.js";

const wrap = (ui) =>
    render(
        <MantineProvider theme={theme} forceColorScheme="light">
            {ui}
        </MantineProvider>,
    );

describe("theme", () => {
    it("counter-scales the 14px root font so Mantine rems land on their px values", () => {
        expect(theme.scale).toBeCloseTo(16 / 14);
        expect(theme.defaultRadius).toBe("6px");
        expect(theme.cursorType).toBe("pointer");
    });

    it("gives buttons the app's own size instead of Mantine's default", () => {
        expect(theme.components.Button.defaultProps.size).toBe("m");
        wrap(<Button>Go</Button>);
        expect(screen.getByRole("button", { name: "Go" }).className).toContain("Button");
    });

    it("keeps a select from deselecting and puts the check on the right", () => {
        const props = theme.components.Select.defaultProps;
        expect(props.allowDeselect).toBe(false);
        expect(props.checkIconPosition).toBe("right");
        expect(props.withScrollArea).toBe(false);
        expect(props.comboboxProps).toEqual({ shadow: "md", offset: 4 });
    });

    it("centres modals and keeps their transition short", () => {
        const props = theme.components.Modal.defaultProps;
        expect(props.centered).toBe(true);
        expect(props.transitionProps.duration).toBe(100);
        expect(props.overlayProps.backgroundOpacity).toBe(0.5);
        wrap(<Modal opened onClose={() => {}} title="Hi" />);
        expect(screen.getByText("Hi")).toBeInTheDocument();
    });

    it("drops the tooltip arrow and anchors menus below their target", () => {
        expect(theme.components.Tooltip.defaultProps.withArrow).toBe(false);
        expect(theme.components.Menu.defaultProps.position).toBe("bottom");
        expect(theme.components.Menu.defaultProps.offset).toBe(4);
    });
});
