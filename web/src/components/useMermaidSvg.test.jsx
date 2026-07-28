import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderUI, screen, waitFor } from "../test/render.jsx";

const mermaid = { initialize: vi.fn(), render: vi.fn() };
vi.mock("mermaid", () => ({ default: mermaid }));
vi.mock("@mantine/core", async (importOriginal) => ({
    ...(await importOriginal()),
    useComputedColorScheme: vi.fn(() => "light"),
}));

import { naturalSize, useMermaidSvg } from "./useMermaidSvg.js";
import { useComputedColorScheme } from "@mantine/core";

function Probe({ chart }) {
    const { svg, failed } = useMermaidSvg(chart);
    return <output data-failed={failed}>{svg}</output>;
}

describe("naturalSize", () => {
    it("reads valid viewBox dimensions and rejects incomplete SVGs", () => {
        expect(naturalSize({ viewBox: { baseVal: { width: 640, height: 320 } } })).toEqual({
            width: 640,
            height: 320,
        });
        expect(naturalSize({ viewBox: { baseVal: { width: 0, height: 320 } } })).toBeNull();
        expect(naturalSize({ viewBox: { baseVal: { width: 640, height: 0 } } })).toBeNull();
        expect(naturalSize({ viewBox: {} })).toBeNull();
        expect(naturalSize(null)).toBeNull();
    });
});

describe("useMermaidSvg", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        useComputedColorScheme.mockReturnValue("light");
    });

    it("configures Mermaid for the current scheme and renders its SVG", async () => {
        mermaid.render.mockResolvedValue({ svg: '<svg aria-label="diagram" />' });
        renderUI(<Probe chart="flowchart LR" />);

        await waitFor(() => expect(screen.getByText(/svg aria-label/)).toBeInTheDocument());
        expect(mermaid.initialize).toHaveBeenCalledWith({
            startOnLoad: false,
            securityLevel: "strict",
            theme: "neutral",
            fontFamily: "var(--g-font-family-monospace, ui-monospace, monospace)",
        });
        expect(mermaid.render).toHaveBeenCalledWith(
            expect.stringMatching(/^mermaid-[A-Za-z0-9]+-1$/),
            "flowchart LR",
        );
    });

    it("uses Mermaid's dark theme and re-renders when either input changes", async () => {
        useComputedColorScheme.mockReturnValue("dark");
        mermaid.render
            .mockResolvedValueOnce({ svg: "<svg>one</svg>" })
            .mockResolvedValueOnce({ svg: "<svg>two</svg>" });
        const { rerender } = renderUI(<Probe chart="one" />);
        await screen.findByText("<svg>one</svg>");
        rerender(<Probe chart="two" />);
        await screen.findByText("<svg>two</svg>");

        expect(mermaid.initialize).toHaveBeenLastCalledWith(
            expect.objectContaining({ theme: "dark" }),
        );
        expect(mermaid.render).toHaveBeenLastCalledWith(expect.stringMatching(/-2$/), "two");
    });

    it("never lets a slow earlier render paint over the newer diagram", async () => {
        let settleFirst;
        mermaid.render
            .mockReturnValueOnce(
                new Promise((resolve) => {
                    settleFirst = resolve;
                }),
            )
            .mockResolvedValueOnce({ svg: "<svg>second</svg>" });
        const { rerender } = renderUI(<Probe chart="first" />);
        rerender(<Probe chart="second" />);
        await screen.findByText("<svg>second</svg>");

        // the first render finally comes back — it is stale and must be dropped
        settleFirst({ svg: "<svg>first</svg>" });
        await Promise.resolve();
        await waitFor(() =>
            expect(screen.getByRole("status")).toHaveTextContent("<svg>second</svg>"),
        );
        expect(screen.queryByText("<svg>first</svg>")).not.toBeInTheDocument();
    });

    it("keeps a stale failure from marking the newer diagram as broken", async () => {
        let rejectFirst;
        mermaid.render
            .mockReturnValueOnce(
                new Promise((resolve, reject) => {
                    rejectFirst = reject;
                }),
            )
            .mockResolvedValueOnce({ svg: "<svg>good</svg>" });
        const { rerender } = renderUI(<Probe chart="first" />);
        rerender(<Probe chart="second" />);
        await screen.findByText("<svg>good</svg>");

        rejectFirst(new Error("stale failure"));
        await Promise.resolve();
        await waitFor(() =>
            expect(screen.getByRole("status")).toHaveAttribute("data-failed", "false"),
        );
    });

    it("reports render errors and clears the error when a new render starts", async () => {
        mermaid.render
            .mockRejectedValueOnce(new Error("bad chart"))
            .mockResolvedValueOnce({ svg: "<svg>fixed</svg>" });
        const { rerender } = renderUI(<Probe chart="bad" />);
        await waitFor(() =>
            expect(screen.getByRole("status")).toHaveAttribute("data-failed", "true"),
        );
        rerender(<Probe chart="fixed" />);
        expect(screen.getByRole("status")).toHaveAttribute("data-failed", "false");
        await screen.findByText("<svg>fixed</svg>");
    });
});
