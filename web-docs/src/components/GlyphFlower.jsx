import { useEffect, useRef } from "react";

const GLYPHS = "0123456789₽¥01";

const fract = (v) => v - Math.floor(v);
const noise = (x, y) => fract(Math.sin(x * 12.9898 + y * 78.233) * 43758.5453);
const smooth = (x, y) =>
    (Math.sin(x * 2.1) + Math.sin(y * 1.7 + 3) + Math.sin((x + y) * 1.3 + 7)) / 3;

function parseColor(value) {
    const v = value.trim();
    if (v.startsWith("#")) {
        const hex = v.length === 4 ? [...v.slice(1)].map((c) => c + c).join("") : v.slice(1);
        return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
    }
    const m = v.match(/(\d+)[, ]+(\d+)[, ]+(\d+)/);
    return m ? [+m[1], +m[2], +m[3]] : [10, 10, 10];
}

export default function GlyphFlower() {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return undefined;
        const box = canvas.parentElement;
        const ctx = canvas.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        let W = 0;
        let H = 0;
        let cells = [];
        let raf = 0;
        let running = false;

        const build = () => {
            W = canvas.width = box.clientWidth * dpr;
            H = canvas.height = box.clientHeight * dpr;
            const cs = Math.max(8, Math.round(W / 46));
            const cx = W * 0.5;
            const cy = H * 0.44;
            const R = Math.min(W, H) * 0.46;
            cells = [];
            for (let gy = 0; gy < H / cs; gy++) {
                for (let gx = 0; gx < W / cs; gx++) {
                    const x = gx * cs + cs / 2;
                    const y = gy * cs + cs / 2;
                    const dx = x - cx;
                    const dy = y - cy;
                    const r = Math.hypot(dx, dy);
                    const th = Math.atan2(dy, dx);
                    const wob = 1 + smooth(Math.cos(th) * 3, Math.sin(th) * 3) * 0.12;
                    const petal = 0.42 + 0.58 * Math.pow(Math.abs(Math.cos(th * 2.5 + 0.4)), 0.55);
                    const edge = R * petal * wob;
                    const inFlower = r < edge;
                    const inStem =
                        y > cy + R * 0.5 &&
                        y < H - cs &&
                        Math.abs(dx + Math.sin((y / H) * 6) * W * 0.008) < cs * 0.8;
                    if (!inFlower && !inStem) continue;
                    const n = noise(gx * 0.7, gy * 0.7);
                    const depth = inFlower ? r / edge : 0.5;
                    const core = inFlower ? Math.max(0, 1 - r / (R * 0.42)) : 0;
                    const rim = inFlower ? Math.pow(depth, 7) * 0.5 : 0;
                    const bright =
                        0.18 +
                        0.55 * Math.pow(n, 1.9) +
                        0.26 * Math.max(0, smooth(gx * 0.24, gy * 0.24)) +
                        rim +
                        (inStem ? 0.15 : 0);
                    cells.push({
                        x,
                        y,
                        ch: GLYPHS[Math.floor(n * GLYPHS.length) % GLYPHS.length],
                        b: Math.min(1, bright),
                        core,
                        tw: n * 6.28,
                        cs,
                    });
                }
            }
        };

        const paint = (t) => {
            const styles = getComputedStyle(box);
            const ink = parseColor(styles.getPropertyValue("--m-text"));
            const acc = parseColor(styles.getPropertyValue("--m-accent"));
            ctx.clearRect(0, 0, W, H);
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            for (const p of cells) {
                const flick = t ? 0.82 + 0.18 * Math.sin(t * 0.0012 + p.tw) : 1;
                const b = p.b * flick;
                ctx.font =
                    (b > 0.55 ? "700 " : "400 ") +
                    p.cs * 0.86 +
                    "px ui-monospace, Menlo, monospace";
                if (p.core > 0.08) {
                    const g = Math.min(1, p.core * 1.4);
                    ctx.fillStyle = `rgba(${acc[0]},${Math.round(acc[1] * (0.6 + 0.4 * g))},${
                        acc[2]
                    },${Math.min(1, b * 0.5 + p.core * 0.6)})`;
                } else {
                    ctx.fillStyle = `rgba(${ink[0]},${ink[1]},${ink[2]},${b * 0.85})`;
                }
                ctx.fillText(p.ch, p.x, p.y);
            }
        };

        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const loop = (t) => {
            paint(t);
            raf = requestAnimationFrame(loop);
        };

        build();
        paint(0);

        const onResize = () => {
            build();
            paint(0);
        };
        window.addEventListener("resize", onResize);

        const mo = new MutationObserver(() => paint(0));
        mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

        let io;
        if (!reduced) {
            io = new IntersectionObserver(([entry]) => {
                if (entry.isIntersecting && !running) {
                    running = true;
                    raf = requestAnimationFrame(loop);
                } else if (!entry.isIntersecting && running) {
                    running = false;
                    cancelAnimationFrame(raf);
                }
            });
            io.observe(box);
        }

        return () => {
            io?.disconnect();
            mo.disconnect();
            cancelAnimationFrame(raf);
            window.removeEventListener("resize", onResize);
        };
    }, []);

    return <canvas className="bloom__canvas" ref={canvasRef} aria-hidden="true" />;
}
