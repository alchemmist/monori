import { ArrowUpRightFromSquare } from "@gravity-ui/icons";
import { useMermaidSvg } from "./useMermaidSvg.js";

export default function Mermaid({
    chart,
    fullscreenHref,
}: {
    chart: string;
    fullscreenHref?: string;
}) {
    const { svg, failed } = useMermaidSvg(chart);

    // until the engine lands (and if the diagram is broken) the source stays
    // readable rather than leaving a blank hole in the page
    if (failed || svg === "")
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
                // nosemgrep: typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml -- mermaid runs at securityLevel "strict" (its bundled dompurify sanitizes the svg) and the source is repo-authored docs, not user input
                dangerouslySetInnerHTML={{ __html: svg }}
            />
            {fullscreenHref != null && fullscreenHref !== "" && (
                <a
                    className="md-mermaid__open"
                    href={fullscreenHref}
                    target="_blank"
                    rel="noreferrer"
                    title="Open the diagram full screen"
                    aria-label="Open the diagram full screen"
                >
                    <ArrowUpRightFromSquare width={14} height={14} />
                </a>
            )}
        </figure>
    );
}
