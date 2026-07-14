import { Link } from "react-router-dom";
import { Icon } from "@gravity-ui/uikit";
import {
  Envelope,
  ArrowDownToLine,
  CurlyBrackets,
  ShieldKeyhole,
  ChartColumn,
  CircleRuble,
  ArrowRight,
  Sparkles,
  LogoGithub,
  LogoDocker,
} from "@gravity-ui/icons";
import Wordmark from "./Wordmark.jsx";

const GITHUB_URL = "https://github.com/alchemmist/monori";
const DEMO_URL = "/demo";

const FEATURES = [
  {
    icon: Envelope,
    title: "Envelope budgeting",
    text: "Hand money to categories, spend them down, roll the rest forward. The exact YNAB-style math of the spreadsheet it grew from.",
    to: "/budgeting",
  },
  {
    icon: ArrowDownToLine,
    title: "Bank-statement import",
    text: "Paste a statement and it parses, auto-categorizes from your keywords, and de-duplicates — preview before anything is written.",
    to: "/importing",
  },
  {
    icon: ChartColumn,
    title: "Dashboard & analytics",
    text: "KPIs, trends, plan-vs-fact, budget discipline, spending patterns and top merchants — derived live from your ledger.",
    to: "/dashboard-analytics",
  },
  {
    icon: CurlyBrackets,
    title: "Full REST API",
    text: "Every action the UI takes is an HTTP call. Groups, categories, transactions, budgets, import — with optional bearer-token auth.",
    to: "/api",
  },
  {
    icon: CircleRuble,
    title: "Integer-kopeck money",
    text: "Every amount is a whole number of kopecks end to end. No floating point, no rounding drift — totals always reconcile.",
    to: "/data-model",
  },
  {
    icon: ShieldKeyhole,
    title: "Self-hosted & private",
    text: "One container, one SQLite file. Your data never leaves your server. Back it up by copying a single file.",
    to: "/configuration",
  },
];

function HeroVisual() {
  const rows = [
    { name: "Groceries", budget: "12 000", act: "−8 450", bal: "3 550", pct: 70, over: false },
    { name: "Transport", budget: "4 000", act: "−4 380", bal: "−380", pct: 100, over: true },
    { name: "Eating out", budget: "6 000", act: "−2 110", bal: "3 890", pct: 35, over: false },
  ];
  return (
    <div className="hero-visual" aria-hidden="true">
      <div className="hero-card">
        <div className="hero-card__head">
          <span>Budget · July</span>
          <span className="hero-card__tbb num">to&nbsp;budget 18 200 ₽</span>
        </div>
        {rows.map((r) => (
          <div className="hero-row" key={r.name}>
            <div className="hero-row__top">
              <span className="hero-row__name">{r.name}</span>
              <span className="num hero-row__budget">{r.budget}</span>
              <span className={`num hero-row__act ${r.over ? "is-over" : ""}`}>{r.act}</span>
              <span className={`num hero-row__bal ${r.over ? "is-neg" : ""}`}>{r.bal}</span>
            </div>
            <div className="hero-row__bar">
              <span
                className={`hero-row__fill ${r.over ? "is-over" : ""}`}
                style={{ width: `${r.pct}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <div className="landing">
      <section className="hero">
        <div className="hero__copy">
          <span className="hero__eyebrow">Self-hosted · single-user · open source</span>
          <h1 className="hero__title">
            Your budget, <span className="accent">to the last kopeck.</span>
          </h1>
          <p className="hero__lede">
            monori is an envelope-budgeting app you run yourself — the YNAB-style workflow of a
            spreadsheet, rebuilt as a fast web app. Integer-kopeck money, bank-statement import, a
            full-year grid, dashboards, and a REST API.
          </p>
          <div className="hero__cta">
            <a className="btn btn_primary" href={DEMO_URL}>
              <Icon data={Sparkles} size={16} />
              Try the live demo
            </a>
            <Link className="btn btn_ghost" to="/getting-started">
              Get started
              <Icon data={ArrowRight} size={16} />
            </Link>
            <a className="btn btn_text" href={GITHUB_URL} target="_blank" rel="noreferrer">
              <Icon data={LogoGithub} size={16} />
              GitHub
            </a>
          </div>
        </div>
        <HeroVisual />
      </section>

      <section className="features">
        {FEATURES.map((f) => (
          <Link className="feature" to={f.to} key={f.title}>
            <span className="feature__icon">
              <Icon data={f.icon} size={20} />
            </span>
            <h3 className="feature__title">{f.title}</h3>
            <p className="feature__text">{f.text}</p>
            <span className="feature__more">
              Learn more <Icon data={ArrowRight} size={13} />
            </span>
          </Link>
        ))}
      </section>

      <section className="model">
        <div className="model__copy">
          <h2 className="model__title">The whole model in three lines</h2>
          <p className="model__text">
            monori is a faithful port of a spreadsheet budget. Its math is small enough to read in
            full — carry, overspend, and the pool left to assign.
          </p>
          <Link className="btn btn_ghost" to="/budgeting">
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

      <section className="cta-band">
        <div>
          <h2 className="cta-band__title">Run it in one container.</h2>
          <p className="cta-band__text">
            A single Docker image serves the app and the API; your budget lives in one SQLite file.
          </p>
        </div>
        <div className="cta-band__actions">
          <Link className="btn btn_primary" to="/getting-started">
            <Icon data={LogoDocker} size={16} />
            Deploy monori
          </Link>
          <Link className="btn btn_ghost" to="/configuration">
            Configuration
          </Link>
        </div>
      </section>

      <footer className="docs-footer">
        <div className="docs-footer__brand">
          <Wordmark size={20} />
          <span>docs</span>
        </div>
        <div className="docs-footer__links">
          <Link to="/getting-started">Getting started</Link>
          <Link to="/api">API</Link>
          <Link to="/development">Contributing</Link>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
        <span className="docs-footer__copy">MIT © alchemmist</span>
      </footer>
    </div>
  );
}
