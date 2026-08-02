import { ArrowLeft, Compass, House } from "@gravity-ui/icons";
import { Link, useLocation } from "react-router-dom";
import "./not-found.css";

const SEEDS = [
    { left: "7%", height: 48, delay: "-1.1s", tone: "muted" },
    { left: "15%", height: 72, delay: "-2.4s", tone: "dark" },
    { left: "23%", height: 38, delay: "-0.4s", tone: "accent" },
    { left: "31%", height: 58, delay: "-1.8s", tone: "muted" },
    { left: "43%", height: 82, delay: "-3.1s", tone: "dark" },
    { left: "54%", height: 45, delay: "-0.8s", tone: "accent" },
    { left: "64%", height: 66, delay: "-2.1s", tone: "muted" },
    { left: "75%", height: 52, delay: "-1.4s", tone: "dark" },
    { left: "86%", height: 75, delay: "-2.8s", tone: "accent" },
    { left: "94%", height: 42, delay: "-0.2s", tone: "muted" },
] as const;

function isDemoPath(pathname: string) {
    return pathname === "/demo" || pathname.startsWith("/demo/");
}

export default function NotFound() {
    const { pathname } = useLocation();
    const demo = isDemoPath(pathname);
    const budgetPath = demo ? "/demo/budget" : "/budget";

    return (
        <main className="not-found" aria-labelledby="not-found-title">
            <div className="not-found__grain" aria-hidden="true" />
            <div className="not-found__grid" aria-hidden="true" />
            <div className="not-found__orbit not-found__orbit_outer" aria-hidden="true" />
            <div className="not-found__orbit not-found__orbit_inner" aria-hidden="true" />

            <header className="not-found__topbar">
                <Link className="not-found__brand" to={budgetPath} aria-label="Go to Budget">
                    もの<span>り</span>
                </Link>
                <span className="not-found__status">
                    <span className="not-found__status-dot" /> route not found
                </span>
            </header>

            <section className="not-found__content">
                <div className="not-found__copy">
                    <p className="not-found__eyebrow">
                        <Compass width={14} height={14} /> lost in the ledger
                    </p>
                    <h1 id="not-found-title" className="not-found__title" aria-label="404">
                        <span>4</span>
                        <span className="not-found__title-zero">0</span>
                        <span>4</span>
                    </h1>
                    <p className="not-found__message">
                        The page you were looking for took a different route.
                    </p>
                    <div className="not-found__actions">
                        <Link className="not-found__button" to={budgetPath}>
                            <House width={15} height={15} />
                            Open Budget
                        </Link>
                        <button
                            className="not-found__back"
                            type="button"
                            onClick={() => window.history.back()}
                        >
                            <ArrowLeft width={14} height={14} />
                            Go back
                        </button>
                    </div>
                </div>

                <div className="not-found__map" aria-hidden="true">
                    <svg className="not-found__route" viewBox="0 0 520 260" fill="none">
                        <path d="M24 211C103 212 88 95 182 107S248 224 334 173s52-128 162-112" />
                        <path
                            className="not-found__route-trace"
                            d="M24 211C103 212 88 95 182 107S248 224 334 173s52-128 162-112"
                        />
                        <circle cx="24" cy="211" r="7" />
                        <circle cx="496" cy="61" r="7" />
                    </svg>
                    <span className="not-found__pin not-found__pin_one">you are here</span>
                    <span className="not-found__pin not-found__pin_two">?</span>
                </div>
            </section>

            <div className="not-found__meadow" aria-hidden="true">
                {SEEDS.map((seed) => (
                    <span
                        className={`not-found__seed not-found__seed_${seed.tone}`}
                        key={seed.left}
                        style={{
                            left: seed.left,
                            height: `${seed.height}px`,
                            animationDelay: seed.delay,
                        }}
                    >
                        <i />
                    </span>
                ))}
            </div>

            <footer className="not-found__footer">
                <span>error / 404</span>
                <span>monori navigation system</span>
            </footer>
        </main>
    );
}
