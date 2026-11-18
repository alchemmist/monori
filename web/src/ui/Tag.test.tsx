import { describe, expect, it } from "vitest";
import Tag from "./Tag.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("Tag", () => {
    it("falls back to the unknown theme", () => {
        renderUI(<Tag>draft</Tag>);
        const el = screen.getByText("draft");
        expect(el.tagName).toBe("SPAN");
        expect(el).toHaveClass("tag", "tag_unknown");
    });

    it("carries the given theme and extra classes", () => {
        renderUI(
            <Tag theme="danger" className="mine">
                over
            </Tag>,
        );
        expect(screen.getByText("over")).toHaveClass("tag", "tag_danger", "mine");
    });

    it("leaves no trailing space when no extra class is given", () => {
        renderUI(<Tag theme="success">ok</Tag>);
        expect(screen.getByText("ok").getAttribute("class")).toBe("tag tag_success");
    });

    it("forwards arbitrary attributes to the span", () => {
        renderUI(
            <Tag title="hint" data-kind="chip">
                x
            </Tag>,
        );
        const el = screen.getByTitle("hint");
        expect(el).toHaveAttribute("data-kind", "chip");
    });
});
