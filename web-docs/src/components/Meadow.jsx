import { useEffect, useRef } from "react";
import "./meadow.css";

const LAYERS = [
    {
        cls: "meadow__layer meadow__layer_back",
        height: 225,
        step: 30,
        spread: 14,
        minH: 34,
        maxH: 105,
        amp: 1.8,
        scale: 0.85,
        inks: ["#dedcd6", "#d3d2cb", "#c8c7bf"],
        petal: "#f3b795",
        core: "#c9c8c2",
        seedOrange: 0.12,
        maxBend: 5,
    },
    {
        cls: "meadow__layer meadow__layer_mid",
        height: 260,
        step: 26,
        spread: 16,
        minH: 48,
        maxH: 155,
        amp: 2.6,
        scale: 1,
        inks: ["#b9b8b0", "#a9a8a0", "#9b9a91"],
        petal: "#f08b54",
        core: "#8a8983",
        seedOrange: 0.28,
        maxBend: 9,
    },
    {
        cls: "meadow__layer meadow__layer_front",
        height: 295,
        step: 23,
        spread: 18,
        minH: 65,
        maxH: 225,
        amp: 3.4,
        scale: 1.12,
        inks: ["#1a1a1a", "#302f2b", "#454440", "#575650"],
        petal: "#ef5a17",
        core: "#1a1a1a",
        seedOrange: 0.42,
        maxBend: 14,
    },
];

const NS = "http://www.w3.org/2000/svg";
const rnd = (a, b) => a + Math.random() * (b - a);
const pick = (a) => a[Math.floor(Math.random() * a.length)];

function grow(svg, o) {
    const W = svg.clientWidth || window.innerWidth;
    const H = o.height;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.innerHTML = "";
    const mk = (n) => document.createElementNS(NS, n);
    const blade = (g, bx, h) => {
        const lean = rnd(-h * 0.4, h * 0.4);
        const w = rnd(1.4, 3.2) * o.scale;
        const p = mk("path");
        p.setAttribute(
            "d",
            `M ${bx - w} ${H} Q ${bx + lean * 0.3} ${H - h * 0.6} ${bx + lean} ${H - h} Q ${bx + lean * 0.42} ${H - h * 0.55} ${bx + w} ${H} Z`,
        );
        p.setAttribute("fill", pick(o.inks));
        g.appendChild(p);
    };
    const stem = (g, bx, h, w) => {
        const p = mk("path");
        p.setAttribute(
            "d",
            `M ${bx - w} ${H} L ${bx - w * 0.4} ${H - h} L ${bx + w * 0.4} ${H - h} L ${bx + w} ${H} Z`,
        );
        p.setAttribute("fill", pick(o.inks));
        g.appendChild(p);
    };
    const leaf = (g, cx, cy, len, ang, ink) => {
        const e = mk("ellipse");
        e.setAttribute("cx", cx);
        e.setAttribute("cy", cy);
        e.setAttribute("rx", len);
        e.setAttribute("ry", len * 0.3);
        e.setAttribute("transform", `rotate(${ang} ${cx} ${cy})`);
        e.setAttribute("fill", ink);
        g.appendChild(e);
    };
    const dot = (g, cx, cy, r, fill) => {
        const c = mk("circle");
        c.setAttribute("cx", cx);
        c.setAttribute("cy", cy);
        c.setAttribute("r", r);
        c.setAttribute("fill", fill);
        g.appendChild(c);
    };
    for (let x = -20; x < W + 20; x += rnd(o.step * 0.5, o.step * 1.25)) {
        const g = mk("g");
        g.setAttribute("class", "meadow__sway");
        g.dataset.x = x.toFixed(1);
        g.style.setProperty("--d", rnd(2.4, 5).toFixed(2) + "s");
        g.style.setProperty("--a", rnd(1, o.amp).toFixed(2) + "deg");
        g.style.setProperty("--del", (-rnd(0, 5)).toFixed(2) + "s");
        const t = Math.random();
        if (t < 0.42) {
            const n = Math.round(rnd(7, 14));
            for (let b = 0; b < n; b++) blade(g, x + rnd(-o.spread, o.spread), rnd(o.minH, o.maxH));
        } else if (t < 0.6) {
            const h = rnd(o.maxH * 0.5, o.maxH * 0.9);
            const ink = pick(o.inks);
            stem(g, x, h, 1.6 * o.scale);
            const n = Math.round(rnd(3, 6));
            for (let k = 0; k < n; k++) {
                const f = 0.3 + (k / n) * 0.65;
                const side = k % 2 ? 1 : -1;
                leaf(
                    g,
                    x + side * rnd(4, 9) * o.scale,
                    H - h * f,
                    rnd(6, 12) * o.scale,
                    side * rnd(20, 50),
                    ink,
                );
            }
        } else if (t < 0.78) {
            const h = rnd(o.maxH * 0.55, o.maxH * 1.0);
            stem(g, x, h, 1.2 * o.scale);
            const orange = Math.random() < o.seedOrange;
            const n = Math.round(rnd(5, 10));
            for (let k = 0; k < n; k++) {
                dot(
                    g,
                    x + rnd(-7, 7) * o.scale,
                    H - h + rnd(-8, 5) * o.scale,
                    rnd(1.4, 3) * o.scale,
                    orange ? o.petal : pick(o.inks),
                );
            }
        } else if (t < 0.9) {
            const ink = pick(o.inks);
            const n = Math.round(rnd(3, 5));
            for (let k = 0; k < n; k++) {
                const h = rnd(o.minH, o.maxH * 0.7);
                const side = k % 2 ? 1 : -1;
                leaf(
                    g,
                    x + side * rnd(2, 8),
                    H - h,
                    rnd(10, 20) * o.scale,
                    side * rnd(35, 70) - 90,
                    ink,
                );
            }
        } else {
            const h = rnd(o.maxH * 0.5, o.maxH * 0.85);
            const r = rnd(5, 9) * o.scale;
            stem(g, x, h, 1.4 * o.scale);
            for (let k = 0; k < 8; k++) {
                const a = (k / 8) * Math.PI * 2;
                const e = mk("ellipse");
                e.setAttribute("cx", x + Math.cos(a) * r);
                e.setAttribute("cy", H - h + Math.sin(a) * r);
                e.setAttribute("rx", r * 0.62);
                e.setAttribute("ry", r * 0.36);
                e.setAttribute(
                    "transform",
                    `rotate(${(a * 180) / Math.PI} ${x + Math.cos(a) * r} ${H - h + Math.sin(a) * r})`,
                );
                e.setAttribute("fill", o.petal);
                g.appendChild(e);
            }
            dot(g, x, H - h, r * 0.5, o.core);
        }
        svg.appendChild(g);
    }
}

export default function Meadow() {
    const ref = useRef(null);

    useEffect(() => {
        const root = ref.current;
        if (!root) return;
        const svgs = Array.from(root.querySelectorAll("svg"));

        const build = () => svgs.forEach((svg, i) => grow(svg, LAYERS[i]));
        build();

        let resizeTimer;
        const onResize = () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(build, 200);
        };
        window.addEventListener("resize", onResize);

        let mx = -9999;
        let my = -9999;
        let raf = null;
        const apply = () => {
            raf = null;
            svgs.forEach((svg, i) => {
                const rect = svg.getBoundingClientRect();
                const cy = rect.bottom - LAYERS[i].height * 0.5;
                svg.querySelectorAll(".meadow__sway").forEach((g) => {
                    const gx = parseFloat(g.dataset.x) + rect.left;
                    const dx = mx - gx;
                    const dy = my - cy;
                    const d = Math.sqrt(dx * dx + dy * dy);
                    if (d < 230) {
                        const f = 1 - d / 230;
                        const dir = dx > 0 ? -1 : 1;
                        g.style.setProperty(
                            "--bend",
                            (dir * f * f * LAYERS[i].maxBend).toFixed(2) + "deg",
                        );
                    } else if (
                        g.style.getPropertyValue("--bend") &&
                        g.style.getPropertyValue("--bend") !== "0deg"
                    ) {
                        g.style.setProperty("--bend", "0deg");
                    }
                });
            });
        };
        const onMove = (e) => {
            mx = e.clientX;
            my = e.clientY;
            if (!raf) raf = requestAnimationFrame(apply);
        };
        const onLeave = () => {
            mx = -9999;
            my = -9999;
            if (!raf) raf = requestAnimationFrame(apply);
        };
        window.addEventListener("mousemove", onMove);
        document.documentElement.addEventListener("mouseleave", onLeave);

        return () => {
            window.removeEventListener("resize", onResize);
            window.removeEventListener("mousemove", onMove);
            document.documentElement.removeEventListener("mouseleave", onLeave);
            if (raf) cancelAnimationFrame(raf);
            clearTimeout(resizeTimer);
        };
    }, []);

    return (
        <div className="meadow" ref={ref} aria-hidden="true">
            <svg className="meadow__layer meadow__layer_back" />
            <svg className="meadow__layer meadow__layer_mid" />
            <svg className="meadow__layer meadow__layer_front" />
        </div>
    );
}
