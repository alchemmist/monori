import { describe, it, expect } from "vitest";
import { stripHtmlComments } from "./content.js";

describe("stripHtmlComments", () => {
    it("drops the generator markers around the schema diagram", () => {
        const src = [
            "intro",
            "",
            "<!-- schema-diagram:start -->",
            "",
            "```mermaid",
            "erDiagram",
            "```",
            "",
            "<!-- schema-diagram:end -->",
            "",
            "outro",
        ].join("\n");
        const out = stripHtmlComments(src);
        expect(out).not.toContain("schema-diagram");
        expect(out).toContain("```mermaid");
        expect(out).toContain("intro");
        expect(out).toContain("outro");
    });

    it("drops a comment that spans several lines", () => {
        expect(stripHtmlComments("a\n<!-- one\ntwo -->\nb")).toBe("a\nb");
    });

    it("leaves ordinary text alone", () => {
        expect(stripHtmlComments("a --> b")).toBe("a --> b");
    });
});
