import { afterEach, describe, expect, it, vi } from "vitest";
import {
    TAB_STRIP_WIDTH,
    TAB_WIDTH,
    computeOffset,
    offsetOf,
    registerTab,
    resizeTab,
    subscribe,
    unregisterTab,
} from "./tabStack.js";

const mounted = [];

function mount(id, width = TAB_WIDTH) {
    registerTab(id, width);
    mounted.push(id);
}

afterEach(() => {
    // the registry is module state and outlives the test file's cases
    while (mounted.length) unregisterTab(mounted.pop());
});

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

    it("handles mixed widths correctly", () => {
        const tabs = [
            { id: "a", width: 100 },
            { id: "b", width: 200 },
            { id: "c", width: 150 },
        ];
        expect(computeOffset(tabs, "a")).toBe(0);
        expect(computeOffset(tabs, "b")).toBe(100);
        expect(computeOffset(tabs, "c")).toBe(300);
    });

    it("returns correct offset for the last tab", () => {
        const tabs = [
            { id: "a", width: 50 },
            { id: "b", width: 60 },
            { id: "c", width: 70 },
        ];
        expect(computeOffset(tabs, "c")).toBe(110);
    });
});

describe("tab registry", () => {
    it("stacks tabs leftwards in mount order", () => {
        mount("a");
        mount("b");
        expect(offsetOf("a")).toBe(0);
        expect(offsetOf("b")).toBe(TAB_WIDTH);
    });

    it("reports zero for a tab that was never registered", () => {
        mount("a");
        expect(offsetOf("ghost")).toBe(TAB_WIDTH);
    });

    it("reflows the stack when a tab is resized", () => {
        mount("a");
        mount("b");
        resizeTab("a", TAB_STRIP_WIDTH);
        expect(offsetOf("b")).toBe(TAB_STRIP_WIDTH);
    });

    it("ignores a resize aimed at an unknown tab", () => {
        mount("a");
        mount("b");
        resizeTab("nope", 10);
        expect(offsetOf("b")).toBe(TAB_WIDTH);
    });

    it("closes the gap when a tab in the middle unregisters", () => {
        mount("a");
        mount("b");
        mount("c");
        unregisterTab("a");
        mounted.splice(mounted.indexOf("a"), 1);
        expect(offsetOf("b")).toBe(0);
        expect(offsetOf("c")).toBe(TAB_WIDTH);
    });

    it("closes the gap when the first tab unregisters", () => {
        mount("a");
        mount("b");
        unregisterTab("a");
        mounted.splice(0, 1);
        expect(offsetOf("b")).toBe(0);
    });

    it("closes the gap when the last tab unregisters", () => {
        mount("a");
        mount("b");
        mount("c");
        unregisterTab("c");
        mounted.pop();
        expect(offsetOf("a")).toBe(0);
        expect(offsetOf("b")).toBe(TAB_WIDTH);
    });

    it("notifies subscribers on every mutation and stops after unsubscribe", () => {
        const fn = vi.fn();
        const off = subscribe(fn);
        mount("a");
        expect(fn).toHaveBeenCalledTimes(1);
        resizeTab("a", 100);
        expect(fn).toHaveBeenCalledTimes(2);
        off();
        unregisterTab("a");
        mounted.pop();
        expect(fn).toHaveBeenCalledTimes(2);
    });

    it("fans out to several subscribers at once", () => {
        const one = vi.fn();
        const two = vi.fn();
        const offOne = subscribe(one);
        const offTwo = subscribe(two);
        mount("a");
        expect(one).toHaveBeenCalledTimes(1);
        expect(two).toHaveBeenCalledTimes(1);
        offOne();
        offTwo();
    });
});
