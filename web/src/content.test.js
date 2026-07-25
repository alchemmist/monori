import { describe, it, expect } from "vitest";
import { stripHtmlComments, mermaidCharts, SECTIONS } from "./content.js";

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

describe("mermaidCharts", () => {
    it("extracts every mermaid fence and nothing else", () => {
        const src = [
            "text",
            "```js",
            "const a = 1;",
            "```",
            "```mermaid",
            "erDiagram",
            "  A ||--o{ B : has",
            "```",
            "more",
            "```mermaid",
            "graph TD",
            "```",
        ].join("\n");
        expect(mermaidCharts(src)).toEqual(["erDiagram\n  A ||--o{ B : has", "graph TD"]);
    });

    it("returns nothing for a page without diagrams", () => {
        expect(mermaidCharts("plain text")).toEqual([]);
        expect(mermaidCharts(undefined)).toEqual([]);
    });

    it("finds the schema diagram on the data model page", () => {
        const page = SECTIONS.find((s) => s.slug === "data-model");
        const charts = mermaidCharts(page.body);
        expect(charts).toHaveLength(1);
        expect(charts[0]).toContain("erDiagram");
    });
});
