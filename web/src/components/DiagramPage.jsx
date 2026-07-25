import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, MagnifierMinus, MagnifierPlus, ArrowsExpand } from "@gravity-ui/icons";
import { sectionBySlug, mermaidCharts } from "../content.js";
import { useMermaidSvg, naturalSize } from "./useMermaidSvg.js";

const MIN_SCALE = 0.1;
const MAX_SCALE = 8;

function clamp(value) {
    return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));
}

export default function DiagramPage() {
    const { slug, index } = useParams();
    const section = sectionBySlug(slug);
    const charts = mermaidCharts(section?.body);
    const chart = charts[Number(index)] ?? "";
    const { svg, failed } = useMermaidSvg(chart);

    const stageRef = useRef(null);
    const canvasRef = useRef(null);
    const [view, setView] = useState({ x: 0, y: 0, k: 1 });
    const [size, setSize] = useState(null);
    const [dragging, setDragging] = useState(false);
    const drag = useRef(null);

    // the size lives in state, not on the svg node: React owns that node through
    // dangerouslySetInnerHTML and would drop any style written straight to it
    useEffect(() => {
        if (svg) setSize(naturalSize(canvasRef.current?.firstElementChild));
    }, [svg]);

    // the diagram is far bigger than the viewport, so it starts fitted and centred
    const fit = useCallback(() => {
        const stage = stageRef.current;
        if (!stage || !size) return;
        const box = stage.getBoundingClientRect();
        const k = clamp(
            Math.min((box.width - 48) / size.width, (box.height - 48) / size.height, 1),
        );
        setView({
            k,
            x: (box.width - size.width * k) / 2,
            y: (box.height - size.height * k) / 2,
        });
    }, [size]);

    useEffect(() => {
        if (size) fit();
    }, [size, fit]);

    // wheel has to be non-passive to keep the browser from scrolling the page
    useEffect(() => {
        const stage = stageRef.current;
        if (!stage) return;
        const onWheel = (e) => {
            e.preventDefault();
            const box = stage.getBoundingClientRect();
            const px = e.clientX - box.left;
            const py = e.clientY - box.top;
            setView((v) => {
                const k = clamp(v.k * Math.exp(-e.deltaY * 0.0015));
                const ratio = k / v.k;
                return { k, x: px - (px - v.x) * ratio, y: py - (py - v.y) * ratio };
            });
        };
        stage.addEventListener("wheel", onWheel, { passive: false });
        return () => stage.removeEventListener("wheel", onWheel);
    }, []);

    const zoomBy = (factor) =>
        setView((v) => {
            const stage = stageRef.current;
            if (!stage) return v;
            const box = stage.getBoundingClientRect();
            const px = box.width / 2;
            const py = box.height / 2;
            const k = clamp(v.k * factor);
            const ratio = k / v.k;
            return { k, x: px - (px - v.x) * ratio, y: py - (py - v.y) * ratio };
        });

    const onPointerDown = (e) => {
        if (e.button !== 0) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
        setDragging(true);
    };

    const onPointerMove = (e) => {
        if (!drag.current) return;
        setView((v) => ({
            ...v,
            x: drag.current.vx + (e.clientX - drag.current.x),
            y: drag.current.vy + (e.clientY - drag.current.y),
        }));
    };

    const endDrag = () => {
        drag.current = null;
        setDragging(false);
    };

    useEffect(() => {
        const onKey = (e) => {
            if (e.key === "0") fit();
            if (e.key === "+" || e.key === "=") zoomBy(1.2);
            if (e.key === "-") zoomBy(1 / 1.2);
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [fit]);

    const back = `/docs/${slug}`;

    return (
        <div className="diagram-page">
            <header className="diagram-page__bar">
                <Link className="diagram-page__back" to={back}>
                    <ArrowLeft width={15} height={15} />
                    <span>{section ? section.title : "Docs"}</span>
                </Link>
                <div className="diagram-page__tools">
                    <button type="button" onClick={() => zoomBy(1 / 1.2)} aria-label="Zoom out">
                        <MagnifierMinus width={15} height={15} />
                    </button>
                    <span className="diagram-page__zoom">{Math.round(view.k * 100)}%</span>
                    <button type="button" onClick={() => zoomBy(1.2)} aria-label="Zoom in">
                        <MagnifierPlus width={15} height={15} />
                    </button>
                    <button type="button" onClick={fit} aria-label="Fit to screen">
                        <ArrowsExpand width={15} height={15} />
                    </button>
                </div>
            </header>

            <div
                className={
                    "diagram-page__stage" + (dragging ? " diagram-page__stage_dragging" : "")
                }
                ref={stageRef}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
            >
                {chart && !failed && svg && (
                    <div
                        className="diagram-page__canvas"
                        ref={canvasRef}
                        style={{
                            width: size ? `${size.width}px` : "auto",
                            height: size ? `${size.height}px` : "auto",
                            transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`,
                        }}
                        // eslint-disable-next-line react/no-danger -- svg comes from mermaid's own renderer
                        dangerouslySetInnerHTML={{ __html: svg }}
                    />
                )}
                {(!chart || failed) && (
                    <p className="diagram-page__empty">
                        {chart ? "This diagram could not be rendered." : "No such diagram."}{" "}
                        <Link to={back}>Back to the page</Link>
                    </p>
                )}
            </div>
        </div>
    );
}
