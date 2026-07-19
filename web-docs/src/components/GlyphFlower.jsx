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

function flowerHead(x, y, cx, cy, R, tilt, petals, phase) {
    const dx = x - cx;
    const dy = y - cy;
    const cos = Math.cos(tilt);
    const sin = Math.sin(tilt);
    const fx = cos * dx + sin * dy;
    const fy = (-sin * dx + cos * dy) / 0.88;
    const r = Math.hypot(fx, fy);
    const th = Math.atan2(fy, fx);
    const wob = 1 + smooth(Math.cos(th) * 3, Math.sin(th) * 3) * 0.12;
    const petal = 0.42 + 0.58 * Math.pow(Math.abs(Math.cos(th * petals + phase)), 0.55);
    const edge = R * petal * wob;
    if (r >= edge) return null;
    return { depth: r / edge, core: Math.max(0, 1 - r / (R * 0.42)) };
}

function nearPolyline(x, y, pts, width) {
    for (let i = 0; i < pts.length - 1; i++) {
        const [ax, ay] = pts[i];
        const [bx, by] = pts[i + 1];
        const vx = bx - ax;
        const vy = by - ay;
        const len2 = vx * vx + vy * vy || 1;
        const t = Math.max(0, Math.min(1, ((x - ax) * vx + (y - ay) * vy) / len2));
        const dx = x - (ax + vx * t);
        const dy = y - (ay + vy * t);
        if (dx * dx + dy * dy < width * width) return true;
    }
    return false;
}

function inLeaf(x, y, lx, ly, ang, len, wid) {
    const cos = Math.cos(ang);
    const sin = Math.sin(ang);
    const u = cos * (x - lx) + sin * (y - ly);
    const v = -sin * (x - lx) + cos * (y - ly);
    if (u < 0 || u > len) return false;
    const half = len / 2;
    const a = (u - half) / half;
    const b = v / wid;
    return a * a + b * b < 1;
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
            const cs = Math.max(7, Math.round(W / 54));
            const cx = W * 0.38;
            const cy = H * 0.27;
            const R = Math.min(W, H) * 0.33;
            const tilt = -0.28;
            const cx2 = W * 0.74;
            const cy2 = H * 0.52;
            const R2 = R * 0.48;

            const stem = [];
            for (let i = 0; i <= 24; i++) {
                const t = i / 24;
                const mt = 1 - t;
                stem.push([
                    mt * mt * (cx - R * 0.18) +
                        2 * mt * t * (cx + W * 0.1) +
                        t * t * (cx - W * 0.02),
                    mt * mt * (cy + R * 0.32) + 2 * mt * t * (cy + (H - cy) * 0.6) + t * t * H,
                ]);
            }
            const sMid = (t) => stem[Math.round(t * 24)];
            const branchFrom = sMid(0.32);
            const branch = [branchFrom, [cx2 + R2 * 0.1, cy2 + R2 * 0.5]];
            const [l1x, l1y] = sMid(0.52);
            const [l2x, l2y] = sMid(0.74);
            const stemW = Math.max(cs * 1.5, W * 0.022);

            cells = [];
            for (let gy = 0; gy < H / cs; gy++) {
                for (let gx = 0; gx < W / cs; gx++) {
                    const x = gx * cs + cs / 2;
                    const y = gy * cs + cs / 2;
                    const head = flowerHead(x, y, cx, cy, R, tilt, 2.5, 0.4);
                    const head2 = head ? null : flowerHead(x, y, cx2, cy2, R2, 0.5, 2.5, 1.1);
                    const hit = head || head2;
                    let kind = hit ? "flower" : "";
                    if (!kind && nearPolyline(x, y, stem, stemW)) kind = "stem";
                    if (!kind && nearPolyline(x, y, branch, stemW * 0.8)) kind = "stem";
                    if (!kind && inLeaf(x, y, l1x, l1y, -0.95, W * 0.2, W * 0.058)) kind = "leaf";
                    if (!kind && inLeaf(x, y, l2x, l2y, Math.PI - 0.5, W * 0.19, W * 0.055))
                        kind = "leaf";
                    if (!kind) continue;
                    const n = noise(gx * 0.7, gy * 0.7);
                    const rim = hit ? Math.pow(hit.depth, 7) * 0.5 : 0;
                    const bright =
                        0.24 +
                        0.55 * Math.pow(n, 1.7) +
                        0.26 * Math.max(0, smooth(gx * 0.24, gy * 0.24)) +
                        rim +
                        (kind === "stem" ? 0.24 : 0) +
                        (kind === "leaf" ? 0.14 : 0);
                    cells.push({
                        x,
                        y,
                        ch: GLYPHS[Math.floor(n * GLYPHS.length) % GLYPHS.length],
                        b: Math.min(1, bright),
                        core: hit ? hit.core : 0,
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
            const light = ink[0] + ink[1] + ink[2] < 380;
            ctx.clearRect(0, 0, W, H);
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            for (const p of cells) {
                const flick = t ? 0.85 + 0.15 * Math.sin(t * 0.0012 + p.tw) : 1;
                const b = p.b * flick;
                ctx.font =
                    (b > 0.55 ? "700 " : "400 ") +
                    p.cs * 0.86 +
                    "px ui-monospace, Menlo, monospace";
                if (p.core > 0.08) {
                    const g = Math.min(1, p.core * 1.4);
                    const coreAlpha = light
                        ? Math.min(1, 0.55 + b * 0.3 + p.core * 0.4)
                        : Math.min(1, b * 0.5 + p.core * 0.6);
                    ctx.fillStyle = `rgba(${acc[0]},${Math.round(acc[1] * (0.6 + 0.4 * g))},${
                        acc[2]
                    },${coreAlpha})`;
                } else {
                    const inkAlpha = light ? 0.42 + b * 0.58 : b * 0.85;
                    ctx.fillStyle = `rgba(${ink[0]},${ink[1]},${ink[2]},${inkAlpha})`;
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
