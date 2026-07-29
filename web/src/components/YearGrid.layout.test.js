import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("year grid viewport", () => {
    it("keeps a fixed viewport height when the number of category rows changes", () => {
        const style = document.createElement("style");
        style.textContent = readFileSync(
            resolve(process.cwd(), "src/components/yeargrid.css"),
            "utf8",
        );
        document.head.appendChild(style);

        const wrapRule = Array.from(style.sheet.cssRules).find(
            (rule) => rule.selectorText === ".year-grid-wrap",
        );

        expect(wrapRule.style.height).toBe(
            "calc(100dvh - var(--yg-top, 200px) - var(--yg-bottom-inset))",
        );
        expect(wrapRule.style.maxHeight).toBe("");

        style.remove();
    });
});
