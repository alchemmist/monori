import { useEffect, useId, useRef, useState } from "react";
import { useComputedColorScheme } from "@mantine/core";

// mermaid is ~half a megabyte, so it is only fetched when a page actually
// contains a diagram, and only once per session
let enginePromise = null;
function loadEngine() {
    if (!enginePromise) enginePromise = import("mermaid").then((m) => m.default);
    return enginePromise;
}

export default function Mermaid({ chart }) {
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
            .then(({ svg }) => {
                if (alive && run === seq.current) setSvg(svg);
            })
            .catch(() => {
                if (alive && run === seq.current) setFailed(true);
            });
        return () => {
            alive = false;
        };
    }, [chart, scheme, id]);

    // until the engine lands (and if the diagram is broken) the source stays
    // readable rather than leaving a blank hole in the page
    if (failed || !svg)
        return (
            <pre className="md-mermaid-src">
                <code>{chart}</code>
            </pre>
        );

    return (
        <div
            className="md-mermaid"
            role="img"
            // eslint-disable-next-line react/no-danger -- svg comes from mermaid's own renderer
            dangerouslySetInnerHTML={{ __html: svg }}
        />
    );
}
