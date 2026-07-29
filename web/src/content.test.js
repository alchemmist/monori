import { describe, it, expect } from "vitest";
import { stripHtmlComments, mermaidCharts, neighbors, sectionBySlug, SECTIONS } from "./content.js";

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

    it("strips a trailing comment even with no newline after it", () => {
        // the closing newline is optional; a marker at the very end of a file
        // still has to go
        expect(stripHtmlComments("text <!-- marker -->")).toBe("text ");
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

    it("tolerates an info string on the fence line", () => {
        // markdown allows text after the language tag; the body still starts on
        // the next line, so it must not be swallowed into the info string
        expect(mermaidCharts("```mermaid theme=dark\ngraph TD\nA-->B\n```")).toEqual([
            "graph TD\nA-->B",
        ]);
    });

    it("finds the schema diagram on the data model page", () => {
        const page = SECTIONS.find((s) => s.slug === "data-model");
        const charts = mermaidCharts(page.body);
        expect(charts).toHaveLength(1);
        expect(charts[0]).toContain("erDiagram");
    });
});

describe("section navigation", () => {
    it("finds known sections and leaves unknown slugs undefined", () => {
        expect(sectionBySlug("budgeting")).toMatchObject({ title: "Budgeting" });
        expect(sectionBySlug("missing")).toBeUndefined();
    });

    it("returns neighboring pages with edge sentinels", () => {
        expect(neighbors(SECTIONS[0].slug)).toMatchObject({ prev: null, next: SECTIONS[1] });
        expect(neighbors(SECTIONS.at(-1).slug)).toMatchObject({
            prev: SECTIONS.at(-2),
            next: null,
        });
        expect(neighbors("missing")).toEqual({ prev: null, next: null });
    });
});
