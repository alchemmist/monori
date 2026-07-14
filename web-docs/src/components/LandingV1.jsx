import { Icon } from "@gravity-ui/uikit";
import { ArrowRight, Wallet, ChartColumn, ChartLine } from "@gravity-ui/icons";
import AmbientField from "./AmbientField.jsx";
import {
  HeroActions,
  FeatureGrid,
  CtaBand,
  DocsFooter,
  VariantSwitcher,
} from "./landingShared.jsx";

const FIELDS = [
  { k: "date", v: "2026-07-13T09:14:02", t: "when" },
  { k: "amount", v: "−4 500", t: "kopecks · signed" },
  { k: "description", v: "“COFFEE POINT”", t: "text" },
  { k: "mcc", v: "5814", t: "merchant class" },
  { k: "hash", v: "9f2c1a…", t: "identity" },
];

const DERIVED = [
  { icon: Wallet, label: "Budget balances" },
  { icon: ChartColumn, label: "Dashboards" },
  { icon: ChartLine, label: "Net worth" },
];

function TransactionRecord() {
  return (
    <div className="rec">
      <div className="rec__title num">transaction</div>
      {FIELDS.map((f) => (
        <div className="rec__row" key={f.k}>
          <span className="rec__key num">{f.k}</span>
          <span className="rec__val num">{f.v}</span>
          <span className="rec__type">{f.t}</span>
        </div>
      ))}
    </div>
  );
}

export default function LandingV1() {
  return (
    <div className="landing landing_v1">
      <VariantSwitcher />

      <section className="hero hero_v1">
        <AmbientField intensity="still" />
        <div className="hero__copy">
          <span className="hero__eyebrow">The data model</span>
          <h1 className="hero__title">
            Your money, <span className="accent">as data you own.</span>
          </h1>
          <p className="hero__lede">
            monori models every payment as one exact event — kopeck-precise, content-addressed, hard
            to duplicate. Budgets, dashboards and net worth are not separate stores; they are views
            computed over that single stream.
          </p>
          <HeroActions />
        </div>

        <div className="hero__stage hero__stage_v1">
          <TransactionRecord />
          <div className="derive">
            <span className="derive__arrow">
              derived <Icon data={ArrowRight} size={13} />
            </span>
            <div className="derive__chips">
              {DERIVED.map((d) => (
                <span className="derive__chip" key={d.label}>
                  <Icon data={d.icon} size={14} />
                  {d.label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="concept">
        <div className="concept__head">
          <span className="concept__eyebrow num">event → model → view</span>
          <h2 className="concept__title">One event. Many honest views.</h2>
          <p className="concept__text">
            Because a transaction carries its own identity and an exact integer amount, every number
            monori shows can be traced back to the events that produced it — no floating-point
            drift, no hidden state.
          </p>
        </div>
        <pre className="concept__code num">
          <code>{`balance(cat, m) = max(balance(cat, m-1), 0) + budgeted + outflows
overspent(m)    = Σ min(balance(cat, m), 0)   over expenses
available(m)    = available(m-1) + overspent(m-1)
                + income(m) − budgetedTotal(m)`}</code>
        </pre>
      </section>

      <FeatureGrid />
      <CtaBand />
      <DocsFooter />
    </div>
  );
}
