import {
    Children,
    isValidElement,
    useEffect,
    useMemo,
    type ComponentPropsWithoutRef,
    type ReactElement,
} from "react";
import { useParams, Link, useNavigate, useLocation } from "react-router-dom";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import { ArrowLeft, ArrowRight } from "@gravity-ui/icons";
import { sectionBySlug, neighbors, mermaidCharts } from "../content.js";
import Mermaid from "./Mermaid.jsx";

function toInternal(href?: string): string | null {
    if (!href) return null;
    if (/^https?:\/\//.test(href) || href.startsWith("#") || href.startsWith("mailto:"))
        return null;
    let h = href.replace(/^\.?\//, "").replace(/^docs\//, "");
    h = h.replace(/\.md($|#)/, "$1");
    if (h === "README" || h === "") return "/docs/getting-started";
    return "/docs/" + h;
}

function MdLink({ href, children }: ComponentPropsWithoutRef<"a">) {
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
function makeComponents(slug: string, charts: string[]): Components {
    function MdPre({ children, ...props }: ComponentPropsWithoutRef<"pre">) {
        const code = Children.toArray(children)[0];
        const codeElement = isValidElement(code)
            ? (code as ReactElement<{ className?: string; children?: unknown }>)
            : null;
        const className = codeElement?.props.className ?? "";
        if (/(^|\s)language-mermaid(\s|$)/.test(className)) {
            const rawSource = codeElement?.props.children;
            const source = (typeof rawSource === "string" ? rawSource : "").replace(/\n$/, "");
            const index = charts.indexOf(source);
            return (
                <Mermaid
                    chart={source}
                    {...(index >= 0 ? { fullscreenHref: `/docs/${slug}/diagram/${index}` } : {})}
                />
            );
        }
        return <pre {...props}>{children}</pre>;
    }

    return {
        a: MdLink,
        pre: MdPre,
        table: (props: ComponentPropsWithoutRef<"table">) => (
            <div className="md-table-wrap">
                <table {...props} />
            </div>
        ),
    };
}

export default function MarkdownPage() {
    const { slug } = useParams();
    const activeSlug = slug ?? "";
    const navigate = useNavigate();
    const { hash } = useLocation();
    const section = sectionBySlug(activeSlug);
    const components = useMemo(
        () => makeComponents(activeSlug, mermaidCharts(section?.body ?? "")),
        [activeSlug, section],
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
                        onClick={() => void navigate("/docs/getting-started")}
                    >
                        Back to the docs
                    </button>
                    .
                </p>
            </article>
        );
    }

    const { prev, next } = neighbors(activeSlug);

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
