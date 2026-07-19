import { useEffect, useRef } from "react";

const ENVELOPES = [
    { name: "Groceries", amount: "12 000" },
    { name: "Transport", amount: "4 000" },
    { name: "Eating out", amount: "6 000", hot: true },
    { name: "Savings", amount: "20 000" },
];

export default function EnvelopeHero() {
    const stageRef = useRef(null);
    const canvasRef = useRef(null);

    useEffect(() => {
        const stage = stageRef.current;
        const canvas = canvasRef.current;
        if (!stage || !canvas) return undefined;
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;

        const ctx = canvas.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        let W = 0;
        let H = 0;
        let slots = [];
        let raf = 0;
        let last = 0;
        let running = false;
        const coins = [];

        const size = () => {
            W = canvas.width = stage.clientWidth * dpr;
            H = canvas.height = stage.clientHeight * dpr;
            const sr = stage.getBoundingClientRect();
            slots = [...stage.querySelectorAll(".env-hero__pocket")].map((el) => {
                const r = el.getBoundingClientRect();
                return (r.left + r.width / 2 - sr.left) * dpr;
            });
        };

        const spawn = () => {
            if (!slots.length) return;
            coins.push({
                x: W / 2 + (Math.random() - 0.5) * W * 0.3,
                y: -6 * dpr,
                vx: 0,
                vy: (1.1 + Math.random() * 0.8) * dpr,
                r: (2.6 + Math.random() * 2.2) * dpr,
                slot: slots[Math.floor(Math.random() * slots.length)],
                hot: Math.random() < 0.22,
            });
        };

        const frame = (ts) => {
            if (ts - last > 300) {
                spawn();
                last = ts;
            }
            const styles = getComputedStyle(stage);
            const ink = styles.getPropertyValue("--m-text").trim();
            const accent = styles.getPropertyValue("--m-accent").trim();
            ctx.clearRect(0, 0, W, H);
            const floor = H - 86 * dpr;
            for (let i = coins.length - 1; i >= 0; i--) {
                const p = coins[i];
                p.vx += (p.slot - p.x) * 0.0014;
                p.vx *= 0.985;
                p.x += p.vx;
                p.y += p.vy;
                if (p.y > floor) {
                    coins.splice(i, 1);
                    continue;
                }
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.r, 0, 7);
                ctx.fillStyle = p.hot ? accent : ink;
                ctx.globalAlpha = Math.min(1, (floor - p.y) / (44 * dpr)) * 0.9;
                ctx.fill();
            }
            ctx.globalAlpha = 1;
            raf = requestAnimationFrame(frame);
        };

        const io = new IntersectionObserver(([entry]) => {
            if (entry.isIntersecting && !running) {
                running = true;
                size();
                raf = requestAnimationFrame(frame);
            } else if (!entry.isIntersecting && running) {
                running = false;
                cancelAnimationFrame(raf);
            }
        });
        io.observe(stage);
        window.addEventListener("resize", size);

        return () => {
            io.disconnect();
            cancelAnimationFrame(raf);
            window.removeEventListener("resize", size);
        };
    }, []);

    return (
        <div className="env-hero" ref={stageRef} aria-hidden="true">
            <canvas className="env-hero__canvas" ref={canvasRef} />
            <div className="env-hero__row">
                {ENVELOPES.map((e) => (
                    <div className={`env-hero__env${e.hot ? " is-hot" : ""}`} key={e.name}>
                        <div className="env-hero__pocket">
                            <span className="env-hero__amt num">{e.amount}</span>
                        </div>
                        <span className="env-hero__name">{e.name}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}
