import { useEffect, useId, useRef, useState } from "react";
import { useComputedColorScheme } from "@mantine/core";

// mermaid is ~half a megabyte, so it is only fetched when a page actually
// contains a diagram, and only once per session
type MermaidEngine = (typeof import("mermaid"))["default"];
let enginePromise: Promise<MermaidEngine> | null = null;
function loadEngine(): Promise<MermaidEngine> {
    if (!enginePromise) enginePromise = import("mermaid").then((m) => m.default);
    return enginePromise;
}

// mermaid ships the svg at width="100%" with the real size only in its viewBox,
// so anything that lays it out itself has to read the intrinsic size from there
export function naturalSize(svg: unknown) {
    if (typeof svg !== "object" || svg === null) return null;
    const viewBox: unknown = Reflect.get(svg, "viewBox");
    if (typeof viewBox !== "object" || viewBox === null) return null;
    const box: unknown = Reflect.get(viewBox, "baseVal");
    if (typeof box !== "object" || box === null) return null;
    const width: unknown = Reflect.get(box, "width");
    const height: unknown = Reflect.get(box, "height");
    if (typeof width !== "number" || typeof height !== "number" || width === 0 || height === 0)
        return null;
    return { width, height };
}

export function useMermaidSvg(chart: string) {
    const scheme = useComputedColorScheme("light");
    const [svg, setSvg] = useState("");
    const [failed, setFailed] = useState(false);
    // mermaid ids end up in the DOM as element ids; useId's colons are not valid there
    const id = "mermaid-" + useId().replace(/[^a-zA-Z0-9]/g, "");
    const seq = useRef(0);

    useEffect(() => {
        let alive = true;
        const run = ++seq.current;
        setFailed(false);
        loadEngine()
            .then((mermaid) => {
                mermaid.initialize({
                    startOnLoad: false,
                    securityLevel: "strict",
                    theme: scheme === "dark" ? "dark" : "neutral",
                    fontFamily: "var(--g-font-family-monospace, ui-monospace, monospace)",
                });
                return mermaid.render(`${id}-${run}`, chart);
            })
            .then((rendered) => {
                if (alive && run === seq.current) setSvg(rendered.svg);
            })
            .catch(() => {
                if (alive && run === seq.current) setFailed(true);
            });
        return () => {
            alive = false;
        };
    }, [chart, scheme, id]);

    return { svg, failed };
}
