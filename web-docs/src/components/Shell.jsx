import { useState } from "react";
import { Outlet, NavLink, Link, useLocation } from "react-router-dom";
import { Icon } from "@gravity-ui/uikit";
import { Sun, Moon, LogoGithub, ArrowUpRightFromSquare, Bars } from "@gravity-ui/icons";
import { NAV } from "../content.js";
import Wordmark from "./Wordmark.jsx";

const GITHUB_URL = "https://github.com/alchemmist/monori";

function SidebarNav({ onNavigate }) {
    return (
        <nav className="docs-side__nav">
            {NAV.map((group) => (
                <div className="docs-side__group" key={group.group}>
                    <div className="docs-side__group-title">{group.group}</div>
                    {group.items.map((item) => (
                        <NavLink
                            key={item.slug}
                            to={`/docs/${item.slug}`}
                            className={({ isActive }) =>
                                `docs-side__link ${isActive ? "docs-side__link_active" : ""}`
                            }
                            onClick={onNavigate}
                        >
                            {item.title}
                        </NavLink>
                    ))}
                </div>
            ))}
        </nav>
    );
}

export default function Shell({ theme, onToggleTheme }) {
    const { pathname } = useLocation();
    const isDoc = pathname.startsWith("/docs");
    const [menuOpen, setMenuOpen] = useState(false);

    return (
        <div className="docs-root">
            <header className="docs-top">
                <div className="docs-top__left">
                    {isDoc && (
                        <button
                            className="docs-top__burger"
                            onClick={() => setMenuOpen((v) => !v)}
                            aria-label="Toggle navigation"
                        >
                            <Icon data={Bars} size={16} />
                        </button>
                    )}
                    <Link to="/welcome" className="docs-top__brand">
                        <Wordmark size={22} />
                        <span className="docs-top__brand-sub">docs</span>
                    </Link>
                </div>
                <div className="docs-top__right">
                    <NavLink to="/docs/getting-started" className="docs-top__link">
                        Documentation
                    </NavLink>
                    <a className="docs-top__link" href="/login" title="Sign in">
                        Sign in
                        <Icon data={ArrowUpRightFromSquare} size={13} />
                    </a>
                    <a
                        className="docs-top__icon"
                        href={GITHUB_URL}
                        target="_blank"
                        rel="noreferrer"
                        aria-label="GitHub"
                    >
                        <Icon data={LogoGithub} size={17} />
                    </a>
                    <button
                        className="docs-top__icon"
                        onClick={onToggleTheme}
                        aria-label="Toggle theme"
                        title="Toggle theme"
                    >
                        <Icon data={theme === "light" ? Moon : Sun} size={17} />
                    </button>
                </div>
            </header>

            {isDoc ? (
                <div className="docs-layout">
                    <aside className={`docs-side ${menuOpen ? "docs-side_open" : ""}`}>
                        <SidebarNav onNavigate={() => setMenuOpen(false)} />
                    </aside>
                    <main className="docs-main">
                        <Outlet />
                    </main>
                </div>
            ) : (
                <Outlet />
            )}
        </div>
    );
}
