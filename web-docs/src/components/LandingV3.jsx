import { Icon } from "@gravity-ui/uikit";
import { ArrowDown } from "@gravity-ui/icons";
import AmbientField from "./AmbientField.jsx";
import {
  HeroActions,
  FeatureGrid,
  CtaBand,
  DocsFooter,
  VariantSwitcher,
} from "./landingShared.jsx";

const INPUTS = ["transactions", "budgets", "snapshot"];
const OUTPUTS = ["balances", "overspent", "available"];
const VIEWS = ["charts", "dashboards", "net worth"];

function BoldBars() {
  const v = [42, 68, 30, 84, 55, 72, 38];
  return (
    <div className="v3chart v3chart_bars" aria-hidden="true">
      {v.map((h, i) => (
        <span key={i} className="v3bar" style={{ height: `${h}%` }} />
      ))}
    </div>
  );
}

export default function LandingV3() {
  return (
    <div className="landing landing_v3">
      <VariantSwitcher />

      <section className="hero hero_v3">
        <AmbientField intensity="bold" />
        <span className="hero__eyebrow">The math is open</span>
        <h1 className="hero__title hero__title_v3">
          A budget you can read
          <br />
          to the <span className="accent">last formula.</span>
        </h1>
        <p className="hero__lede hero__lede_v3">
          Not a black box. monori is one small, pure computation over your transactions and budgets
          — the entire model fits on this screen. What you see is exactly what it does.
        </p>
        <HeroActions />
      </section>

      <section className="pipeline">
        <div className="pipe-row pipe-row_in">
          {INPUTS.map((n) => (
            <span className="pipe-node num" key={n}>
              {n}
            </span>
          ))}
        </div>
        <div className="pipe-arrow">
          <Icon data={ArrowDown} size={18} />
        </div>
        <div className="pipe-compute num">compute( )</div>
        <div className="pipe-arrow">
          <Icon data={ArrowDown} size={18} />
        </div>
        <div className="pipe-row pipe-row_out">
          {OUTPUTS.map((n) => (
            <span className="pipe-node pipe-node_out num" key={n}>
              {n}
            </span>
          ))}
        </div>
        <div className="pipe-arrow">
          <Icon data={ArrowDown} size={18} />
        </div>
        <div className="pipe-views">
          {VIEWS.map((n) => (
            <span className="pipe-view" key={n}>
              {n}
            </span>
          ))}
        </div>
      </section>

      <section className="formula-hero">
        <BoldBars />
        <pre className="formula-hero__code num">
          <code>
            <span className="fline">
              <span className="tok tok_id">balance</span>(cat, m) ={" "}
              <span className="accent">max</span>(balance₋₁, 0) + budgeted + outflows
            </span>
            <span className="fline">
              <span className="tok tok_id">overspent</span>(m) = <span className="accent">Σ</span>{" "}
              min(balance, 0)
            </span>
            <span className="fline">
              <span className="tok tok_id">available</span>(m) = available₋₁ + overspent₋₁ + income
              − budgeted
            </span>
          </code>
        </pre>
      </section>

      <FeatureGrid />
      <CtaBand />
      <DocsFooter />
    </div>
  );
}
