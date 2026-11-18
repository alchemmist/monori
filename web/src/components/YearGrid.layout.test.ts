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

        const wrapRule = Array.from(style.sheet!.cssRules).find(
            (rule): rule is CSSStyleRule =>
                rule instanceof CSSStyleRule && rule.selectorText === ".year-grid-wrap",
        )!;

        try {
            expect(wrapRule.style.height).toContain("100dvh");
            expect(wrapRule.style.height).toContain("--yg-top");
            expect(wrapRule.style.height).toContain("--yg-bottom-inset");
            expect(wrapRule.style.maxHeight).toBe("");
        } finally {
            style.remove();
        }
    });

    it("keeps year-dependent toolbar actions in reserved desktop slots", () => {
        const style = document.createElement("style");
        style.textContent = readFileSync(resolve(process.cwd(), "src/pages/budget.css"), "utf8");
        document.head.appendChild(style);

        try {
            const rules = Array.from(style.sheet!.cssRules).filter(
                (rule): rule is CSSStyleRule => rule instanceof CSSStyleRule,
            );
            const toolbarRule = rules.find((rule) => rule.selectorText === ".budget-toolbar")!;
            const createRule = rules.find(
                (rule) => rule.selectorText === ".budget-toolbar__create",
            )!;
            const unusedRule = rules.find(
                (rule) => rule.selectorText === ".budget-toolbar__unused",
            )!;
            const hiddenRule = rules.find(
                (rule) => rule.selectorText === ".budget-toolbar__action_hidden",
            )!;

            expect(toolbarRule.style.flexWrap).toBe("nowrap");
            expect(createRule.style.width).not.toBe("");
            expect(unusedRule.style.width).not.toBe("");
            expect(hiddenRule.style.visibility).toBe("hidden");
        } finally {
            style.remove();
        }
    });
});
