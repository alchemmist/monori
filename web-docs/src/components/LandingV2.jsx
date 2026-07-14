import { useEffect, useState } from "react";
import AmbientField from "./AmbientField.jsx";
import {
  HeroActions,
  FeatureGrid,
  CtaBand,
  DocsFooter,
  VariantSwitcher,
} from "./landingShared.jsx";

const QUERIES = [
  {
    query: [
      ["kw", "sum"],
      ["p", "(amount) "],
      ["kw", "by "],
      ["id", "category "],
      ["kw", "where "],
      ["id", "mcc "],
      ["op", "= "],
      ["num", "5411"],
    ],
    unit: "₽",
    rows: [
      { label: "Groceries", value: "12 400", pct: 100 },
      { label: "Household", value: "6 900", pct: 56 },
      { label: "Transport", value: "4 380", pct: 35 },
      { label: "Eating out", value: "2 110", pct: 17 },
    ],
  },
  {
    query: [
      ["kw", "sum"],
      ["p", "(amount) "],
      ["kw", "by "],
      ["id", "month "],
      ["kw", "where "],
      ["id", "category "],
      ["op", "= "],
      ["str", '"Salary"'],
    ],
    unit: "₽",
    rows: [
      { label: "May", value: "180 000", pct: 90 },
      { label: "Jun", value: "180 000", pct: 90 },
      { label: "Jul", value: "200 000", pct: 100 },
      { label: "Aug", value: "150 000", pct: 75 },
    ],
  },
  {
    query: [
      ["kw", "count"],
      ["p", "(*) "],
      ["kw", "by "],
      ["id", "weekday"],
    ],
    unit: "tx",
    rows: [
      { label: "Fri", value: "48", pct: 100 },
      { label: "Sat", value: "41", pct: 85 },
      { label: "Mon", value: "29", pct: 60 },
      { label: "Wed", value: "22", pct: 46 },
    ],
  },
];

function QueryConsole() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setI((n) => (n + 1) % QUERIES.length), 3400);
    return () => clearInterval(id);
  }, []);
  const q = QUERIES[i];
  return (
    <div className="qc">
      <div className="qc__bar">
        <span className="qc__dot" />
        <span className="qc__dot" />
        <span className="qc__dot" />
        <span className="qc__name num">selectors</span>
      </div>
      <div className="qc__prompt num">
        <span className="qc__caret">›</span>{" "}
        {q.query.map((tok, k) => (
          <span className={`tok tok_${tok[0]}`} key={k}>
            {tok[1]}
          </span>
        ))}
        <span className="qc__cursor" />
      </div>
      <div className="qc__chart" key={i}>
        {q.rows.map((r) => (
          <div className="qbar" key={r.label}>
            <span className="qbar__label">{r.label}</span>
            <span className="qbar__track">
              <span className="qbar__fill" style={{ width: `${r.pct}%` }} />
            </span>
            <span className="qbar__value num">
              {r.value} <span className="qbar__unit">{q.unit}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LandingV2() {
  return (
    <div className="landing landing_v2">
      <VariantSwitcher />

      <section className="hero hero_v2">
        <AmbientField intensity="living" />
        <div className="hero__copy">
          <span className="hero__eyebrow">Query your money</span>
          <h1 className="hero__title">
            Ask your money <span className="accent">anything.</span>
          </h1>
          <p className="hero__lede">
            Every transaction is a typed row, so slicing it is just a query. A small selector
            language — think metrics-style expressions over your own spending — turns a one-line
            question into a chart.
          </p>
          <HeroActions />
          <p className="hero__note num">planned · monium-style selectors</p>
        </div>
        <div className="hero__stage hero__stage_v2">
          <QueryConsole />
        </div>
      </section>

      <section className="concept concept_center">
        <span className="concept__eyebrow num">event → model → query → chart</span>
        <h2 className="concept__title">The whole point is what comes after import.</h2>
        <p className="concept__text concept__text_wide">
          monori is not just a place to store transactions — it is a place to interrogate them.
          Group by category, month, merchant class or tag; filter on any field; render as bars,
          lines or a donut. The importer fills the table; the selector language reads it back.
        </p>
      </section>

      <FeatureGrid />
      <CtaBand />
      <DocsFooter />
    </div>
  );
}
