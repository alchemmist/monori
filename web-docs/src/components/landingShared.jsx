import { Link, NavLink } from "react-router-dom";
import { Icon } from "@gravity-ui/uikit";
import { ArrowRight, Sparkles, LogoGithub, LogoDocker } from "@gravity-ui/icons";
import Wordmark from "./Wordmark.jsx";
import { FEATURES, GITHUB_URL, DEMO_URL } from "./landingData.js";

export function HeroActions() {
  return (
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
  );
}

export function FeatureGrid() {
  return (
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
  );
}

export function CtaBand() {
  return (
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
  );
}

export function DocsFooter() {
  return (
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
  );
}

const VARIANTS = [
  { to: "/v1", label: "1 · Transaction" },
  { to: "/v2", label: "2 · Selectors" },
  { to: "/v3", label: "3 · Model" },
];

export function VariantSwitcher() {
  return (
    <div className="vswitch" role="navigation" aria-label="Landing variant">
      <span className="vswitch__label">Concept</span>
      {VARIANTS.map((v) => (
        <NavLink
          key={v.to}
          to={v.to}
          className={({ isActive }) => `vswitch__pill ${isActive ? "vswitch__pill_active" : ""}`}
        >
          {v.label}
        </NavLink>
      ))}
    </div>
  );
}
