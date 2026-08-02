import { ArrowLeft, House } from "@gravity-ui/icons";
import { Link, useLocation } from "react-router-dom";
import "./not-found.css";

const SCRAPS = [
    { side: "left", offset: "6%", delay: "-1.5s", duration: "9s", rotate: "-8deg" },
    { side: "left", offset: "21%", delay: "-6.1s", duration: "12s", rotate: "11deg" },
    { side: "right", offset: "8%", delay: "-4.2s", duration: "10s", rotate: "7deg" },
    { side: "right", offset: "24%", delay: "-8.4s", duration: "13s", rotate: "-12deg" },
] as const;

function isDemoPath(pathname: string) {
    return pathname === "/demo" || pathname.startsWith("/demo/");
}

export default function NotFound() {
    const { pathname } = useLocation();
    const budgetPath = isDemoPath(pathname) ? "/demo/budget" : "/budget";

    return (
        <main className="not-found" aria-labelledby="not-found-title">
            <div className="not-found__grain" aria-hidden="true" />

            <header className="not-found__topbar">
                <Link className="not-found__brand" to={budgetPath} aria-label="Go to Budget">
                    もの<span>り</span>
                </Link>
                <span className="not-found__status">
                    <span className="not-found__status-dot" /> transaction declined
                </span>
            </header>

            <div className="not-found__scraps" aria-hidden="true">
                {SCRAPS.map((scrap) => (
                    <span
                        className="not-found__scrap"
                        key={`${scrap.side}-${scrap.offset}`}
                        style={{
                            [scrap.side]: scrap.offset,
                            animationDelay: scrap.delay,
                            animationDuration: scrap.duration,
                            rotate: scrap.rotate,
                        }}
                    >
                        <b>MONORI</b>
                        <i />
                        404
                        <i />
                        route?
                    </span>
                ))}
            </div>

            <section className="not-found__receipt">
                <div className="not-found__receipt-head">
                    <span>monori / navigation</span>
                    <span>#000404</span>
                </div>

                <p className="not-found__receipt-date">PAGE LOOKUP · FINAL RECEIPT</p>
                <h1 id="not-found-title" className="not-found__title">
                    404
                </h1>
                <p className="not-found__message">This page isn't in your ledger.</p>

                <dl className="not-found__rows">
                    <div>
                        <dt>Requested route</dt>
                        <dd className="not-found__declined">NOT FOUND</dd>
                    </div>
                    <div>
                        <dt>Your balance</dt>
                        <dd>still safe</dd>
                    </div>
                    <div>
                        <dt>Pages located</dt>
                        <dd>0</dd>
                    </div>
                    <div className="not-found__total">
                        <dt>Total lost</dt>
                        <dd>0 ₽</dd>
                    </div>
                </dl>

                <div className="not-found__barcode" aria-hidden="true" />
                <p className="not-found__thanks">THANK YOU FOR BUDGETING RESPONSIBLY</p>

                <div className="not-found__actions">
                    <Link className="not-found__button" to={budgetPath}>
                        <House width={15} height={15} />
                        Return to Budget
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
            </section>

            <footer className="not-found__footer">
                <span>error / 404</span>
                <span>no money was lost</span>
            </footer>
        </main>
    );
}
