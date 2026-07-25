import { describe, expect, it } from "vitest";
import { TAB_STRIP_WIDTH, TAB_WIDTH, computeLayer, computeOffset } from "./tabStack.js";

describe("computeOffset", () => {
    it("puts the first tab at the edge and pushes later ones left", () => {
        const tabs = [
            { id: "a", width: TAB_WIDTH },
            { id: "b", width: TAB_WIDTH },
            { id: "c", width: TAB_WIDTH },
        ];
        expect(computeOffset(tabs, "a")).toBe(0);
        expect(computeOffset(tabs, "b")).toBe(TAB_WIDTH);
        expect(computeOffset(tabs, "c")).toBe(TAB_WIDTH * 2);
    });

    it("reflows when an earlier tab collapses to its strip", () => {
        const tabs = [
            { id: "a", width: TAB_STRIP_WIDTH },
            { id: "b", width: TAB_WIDTH },
        ];
        expect(computeOffset(tabs, "b")).toBe(TAB_STRIP_WIDTH);
    });

    it("is zero for an unknown or first tab", () => {
        expect(computeOffset([], "x")).toBe(0);
    });
});

describe("computeLayer", () => {
    it("keeps the tab nearest the edge above the tabs to its left", () => {
        const tabs = [
            { id: "a", width: TAB_WIDTH },
            { id: "b", width: TAB_WIDTH },
            { id: "c", width: TAB_WIDTH },
        ];

        expect(computeLayer(tabs, "a")).toBeGreaterThan(computeLayer(tabs, "b"));
        expect(computeLayer(tabs, "b")).toBeGreaterThan(computeLayer(tabs, "c"));
    });

    it("returns zero for an unknown tab", () => {
        expect(computeLayer([], "x")).toBe(0);
    });
});
