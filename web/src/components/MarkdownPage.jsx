import { useEffect, useMemo } from "react";
import { useParams, Link, useNavigate, useLocation } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import { ArrowLeft, ArrowRight } from "@gravity-ui/icons";
import { sectionBySlug, neighbors, mermaidCharts } from "../content.js";
import Mermaid from "./Mermaid.jsx";

function toInternal(href) {
    if (!href) return null;
    if (/^https?:\/\//.test(href) || href.startsWith("#") || href.startsWith("mailto:"))
        return null;
    let h = href.replace(/^\.?\//, "").replace(/^docs\//, "");
    h = h.replace(/\.md($|#)/, "$1");
    if (h === "README" || h === "") return "/docs/getting-started";
    return "/docs/" + h;
}

function MdLink({ href, children }) {
    const internal = toInternal(href);
    if (internal) return <Link to={internal}>{children}</Link>;
    const external = /^https?:\/\//.test(href || "");
    return (
        <a href={href} {...(external ? { target: "_blank", rel: "noreferrer" } : {})}>
            {children}
        </a>
    );
}

// ```mermaid fences become diagrams; every other fence keeps the plain <pre>
function makeComponents(slug, charts) {
    function MdPre({ children, ...props }) {
        const code = Array.isArray(children) ? children[0] : children;
        const className = code?.props?.className ?? "";
        if (/(^|\s)language-mermaid(\s|$)/.test(className)) {
            const source = String(code.props.children ?? "").replace(/\n$/, "");
            const index = charts.indexOf(source);
            return (
                <Mermaid
                    chart={source}
                    fullscreenHref={index >= 0 ? `/docs/${slug}/diagram/${index}` : null}
                />
            );
        }
        return <pre {...props}>{children}</pre>;
    }

    return {
        a: MdLink,
        pre: MdPre,
        table: (props) => (
            <div className="md-table-wrap">
                <table {...props} />
            </div>
        ),
    };
}

export default function MarkdownPage() {
    const { slug } = useParams();
    const navigate = useNavigate();
    const { hash } = useLocation();
    const section = sectionBySlug(slug);
    const components = useMemo(
        () => makeComponents(slug, mermaidCharts(section?.body)),
        [slug, section],
    );

    useEffect(() => {
        if (hash) {
            const el = document.getElementById(decodeURIComponent(hash.slice(1)));
            if (el) {
                el.scrollIntoView();
                return;
            }
        }
        window.scrollTo(0, 0);
    }, [slug, hash]);

    if (!section) {
        return (
            <article className="md">
                <h1>Not found</h1>
                <p>
                    There is no documentation page called <code>{slug}</code>.{" "}
                    <button
                        className="md-linklike"
                        onClick={() => navigate("/docs/getting-started")}
                    >
                        Back to the docs
                    </button>
                    .
                </p>
            </article>
        );
    }

    const { prev, next } = neighbors(slug);

    return (
        <>
            <article className="md fade-in" key={slug}>
                <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeSlug]}
                    components={components}
                >
                    {section.body}
                </ReactMarkdown>
            </article>

            <nav className="md-pager">
                {prev ? (
                    <Link className="md-pager__btn" to={`/docs/${prev.slug}`}>
                        <ArrowLeft width={15} height={15} />
                        <span>
                            <span className="md-pager__dir">Previous</span>
                            <span className="md-pager__title">{prev.title}</span>
                        </span>
                    </Link>
                ) : (
                    <span />
                )}
                {next && (
                    <Link className="md-pager__btn md-pager__btn_next" to={`/docs/${next.slug}`}>
                        <span>
                            <span className="md-pager__dir">Next</span>
                            <span className="md-pager__title">{next.title}</span>
                        </span>
                        <ArrowRight width={15} height={15} />
                    </Link>
                )}
            </nav>
        </>
    );
}
