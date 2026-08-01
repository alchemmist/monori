import { describe, expect, it } from "vitest";
import Txt from "./Txt.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("Txt", () => {
    it("is an inline span carrying the tone class", () => {
        renderUI(<Txt tone="secondary">hello</Txt>);
        const el = screen.getByText("hello");
        expect(el.tagName).toBe("SPAN");
        expect(el).toHaveClass("t-secondary");
    });

    it("becomes a div with block, and keeps caption and custom classes", () => {
        renderUI(
            <Txt block caption className="mine">
                note
            </Txt>,
        );
        const el = screen.getByText("note");
        expect(el.tagName).toBe("DIV");
        expect(el).toHaveClass("t-caption", "mine");
    });

    it("carries no class at all when unstyled", () => {
        renderUI(<Txt>plain</Txt>);
        expect(screen.getByText("plain")).not.toHaveAttribute("class");
    });
});
