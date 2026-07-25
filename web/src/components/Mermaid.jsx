import { ArrowsExpand } from "@gravity-ui/icons";
import { useMermaidSvg } from "./useMermaidSvg.js";

export default function Mermaid({ chart, fullscreenHref }) {
    const { svg, failed } = useMermaidSvg(chart);

    // until the engine lands (and if the diagram is broken) the source stays
    // readable rather than leaving a blank hole in the page
    if (failed || !svg)
        return (
            <pre className="md-mermaid-src">
                <code>{chart}</code>
            </pre>
        );

    return (
        <figure className="md-mermaid">
            <div
                className="md-mermaid__canvas"
                role="img"
                // eslint-disable-next-line react/no-danger -- svg comes from mermaid's own renderer
                dangerouslySetInnerHTML={{ __html: svg }}
            />
            {fullscreenHref && (
                <a
                    className="md-mermaid__open"
                    href={fullscreenHref}
                    target="_blank"
                    rel="noreferrer"
                    title="Open the diagram full screen"
                >
                    <ArrowsExpand width={14} height={14} />
                    <span>Full screen</span>
                </a>
            )}
        </figure>
    );
}
