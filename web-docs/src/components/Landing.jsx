import { Link } from "react-router-dom";
import { Icon } from "@gravity-ui/uikit";
import {
    ArrowDownToLine,
    ShieldKeyhole,
    ArrowRight,
    Sparkles,
    LogoGithub,
    LogoDocker,
    Persons,
    Copy,
} from "@gravity-ui/icons";
import Wordmark from "./Wordmark.jsx";
import Meadow from "./Meadow.jsx";
import EnvelopeHero from "./EnvelopeHero.jsx";
import GlyphFlower from "./GlyphFlower.jsx";

const GITHUB_URL = "https://github.com/alchemmist/monori";
const DEMO_URL = "/demo";

const SPARK_POINTS = "0,26 8,22 16,24 24,17 32,19 40,12 48,15 56,9 64,12 72,6 80,9 88,3 100,5";

function Sparkline() {
    return (
        <svg
            className="bento__spark"
            viewBox="0 0 100 30"
            preserveAspectRatio="none"
            aria-hidden="true"
        >
            <polygon points={`0,30 ${SPARK_POINTS} 100,30`} className="bento__spark-fill" />
            <polyline points={SPARK_POINTS} className="bento__spark-line" />
        </svg>
    );
}

function MiniRows() {
    return (
        <div className="bento__rows" aria-hidden="true">
            <i style={{ "--w": "70%" }} />
            <i className="is-over" style={{ "--w": "100%" }} />
            <i style={{ "--w": "35%" }} />
        </div>
    );
}

export default function Landing() {
    return (
        <div className="landing">
            <section className="hero">
                <div className="hero__copy">
                    <span className="hero__eyebrow">Self-hosted · multi-user · open source</span>
                    <h1 className="hero__title">
                        Your budget, <span className="accent">to the last kopeck.</span>
                    </h1>
                    <p className="hero__lede">
                        monori is an envelope-budgeting app you run yourself — the YNAB-style
                        workflow of a spreadsheet, rebuilt as a fast web app. Integer-kopeck money,
                        bank-statement import, a full-year grid, dashboards, and a REST API.
                    </p>
                    <div className="hero__cta">
                        <a className="btn btn_primary" href="/login">
                            Sign in
                            <Icon data={ArrowRight} size={16} />
                        </a>
                        <a className="btn btn_ghost" href={DEMO_URL}>
                            <Icon data={Sparkles} size={16} />
                            Try the live demo
                        </a>
                        <Link className="btn btn_ghost" to="/docs/getting-started">
                            Get started
                            <Icon data={ArrowRight} size={16} />
                        </Link>
                        <a
                            className="btn btn_text"
                            href={GITHUB_URL}
                            target="_blank"
                            rel="noreferrer"
                        >
                            <Icon data={LogoGithub} size={16} />
                            GitHub
                        </a>
                    </div>
                </div>
                <EnvelopeHero />
            </section>

            <section className="bento">
                <Link className="bento__tile bento__tile_wide" to="/docs/budgeting">
                    <h3 className="bento__title">Envelope budgeting</h3>
                    <p className="bento__text">
                        Hand money to categories, spend them down, roll the rest forward — the exact
                        YNAB-style math of the spreadsheet it grew from.
                    </p>
                    <MiniRows />
                </Link>
                <Link className="bento__tile bento__tile_orange" to="/docs/data-model">
                    <h3 className="bento__title">Integer kopecks</h3>
                    <b className="bento__big num">0.00 drift</b>
                    <p className="bento__text">No floats. Totals always reconcile.</p>
                </Link>
                <Link className="bento__tile" to="/docs/importing">
                    <span className="bento__icon">
                        <Icon data={ArrowDownToLine} size={18} />
                    </span>
                    <h3 className="bento__title">Statement import</h3>
                    <p className="bento__text">
                        Paste, auto-categorize from your keywords, de-duplicate — preview first.
                    </p>
                </Link>
                <Link className="bento__tile bento__tile_wide" to="/docs/dashboard-analytics">
                    <h3 className="bento__title">Dashboard &amp; analytics</h3>
                    <p className="bento__text">
                        KPIs, trends, plan-vs-fact, spending patterns — derived live from your
                        ledger.
                    </p>
                    <Sparkline />
                </Link>
                <Link className="bento__tile" to="/docs/configuration">
                    <span className="bento__icon">
                        <Icon data={ShieldKeyhole} size={18} />
                    </span>
                    <h3 className="bento__title">Self-hosted &amp; private</h3>
                    <p className="bento__text">
                        One container on your server. Your data never leaves it.
                    </p>
                </Link>
                <Link className="bento__tile" to="/docs/api">
                    <span className="bento__icon">
                        <Icon data={Persons} size={18} />
                    </span>
                    <h3 className="bento__title">Multi-user</h3>
                    <p className="bento__text">
                        Per-user accounts and budgets behind JWT auth — one instance, whole family.
                    </p>
                </Link>
                <Link className="bento__tile bento__tile_wide bento__tile_dark" to="/docs/api">
                    <h3 className="bento__title">Full REST API</h3>
                    <pre className="bento__code">
                        <span className="cmt"># everything the UI does is an HTTP call</span>
                        {"\n"}
                        <span className="acc">GET</span> /api/snapshot{"\n"}
                        <span className="acc">POST</span> /api/transactions
                    </pre>
                </Link>
                <Link className="bento__tile" to="/docs/configuration">
                    <span className="bento__icon">
                        <Icon data={Copy} size={18} />
                    </span>
                    <h3 className="bento__title">One-file backup</h3>
                    <p className="bento__text">
                        The whole ledger is a single SQLite file — <code>cp</code> is a backup.
                    </p>
                </Link>
                <a className="bento__tile" href={GITHUB_URL} target="_blank" rel="noreferrer">
                    <span className="bento__icon">
                        <Icon data={LogoGithub} size={18} />
                    </span>
                    <h3 className="bento__title">Open source</h3>
                    <p className="bento__text">MIT-licensed, built in the open on GitHub.</p>
                </a>
            </section>

            <section className="model">
                <div className="model__copy">
                    <h2 className="model__title">The whole model in three lines</h2>
                    <p className="model__text">
                        monori is a faithful port of a spreadsheet budget. Its math is small enough
                        to read in full — carry, overspend, and the pool left to assign.
                    </p>
                    <Link className="btn btn_ghost" to="/docs/budgeting">
                        How budgeting works
                        <Icon data={ArrowRight} size={15} />
                    </Link>
                </div>
                <pre className="model__code num">
                    <code>
                        {`balance(cat, m)  = max(balance(cat, m-1), 0) + budgeted + outflows
overspent(m)     = Σ min(balance(cat, m), 0)   over expenses
available(m)     = available(m-1) + overspent(m-1)
                 + income(m) - budgetedTotal(m)`}
                    </code>
                </pre>
            </section>

            <section className="bloom">
                <div className="bloom__visual">
                    <GlyphFlower />
                </div>
                <div className="bloom__copy">
                    <span className="bloom__kicker">実り · minori · “harvest”</span>
                    <h2 className="bloom__title">
                        A harvest is planned. <span className="accent">So is money.</span>
                    </h2>
                    <p className="bloom__text">
                        monori is named after the Japanese word for harvest. Every kopeck gets a job
                        before it is spent — planted in an envelope, tended month by month. Nothing
                        guessed, nothing lost.
                    </p>
                    <Link className="btn btn_ghost" to="/docs/getting-started">
                        Start growing
                        <Icon data={ArrowRight} size={15} />
                    </Link>
                </div>
            </section>

            <section className="cta-band">
                <div>
                    <h2 className="cta-band__title">Run it in one container.</h2>
                    <p className="cta-band__text">
                        A single Docker image serves the app and the API; your budget lives in one
                        SQLite file.
                    </p>
                </div>
                <div className="cta-band__actions">
                    <Link className="btn btn_primary" to="/docs/getting-started">
                        <Icon data={LogoDocker} size={16} />
                        Deploy monori
                    </Link>
                    <Link className="btn btn_ghost" to="/docs/configuration">
                        Configuration
                    </Link>
                </div>
            </section>

            <div className="landing__meadow">
                <Meadow />
            </div>

            <footer className="docs-footer">
                <div className="docs-footer__brand">
                    <Wordmark size={20} />
                    <span>docs</span>
                </div>
                <div className="docs-footer__links">
                    <Link to="/docs/getting-started">Getting started</Link>
                    <Link to="/docs/api">API</Link>
                    <Link to="/docs/development">Contributing</Link>
                    <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                        GitHub
                    </a>
                </div>
                <span className="docs-footer__copy">MIT © alchemmist</span>
            </footer>
        </div>
    );
}
