import { useEffect } from "react";
import { useParams, Link, useNavigate, useLocation } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import { Icon } from "@gravity-ui/uikit";
import { ArrowLeft, ArrowRight } from "@gravity-ui/icons";
import { sectionBySlug, neighbors } from "../content.js";

function toInternal(href) {
  if (!href) return null;
  if (/^https?:\/\//.test(href) || href.startsWith("#") || href.startsWith("mailto:")) return null;
  let h = href.replace(/^\.?\//, "").replace(/^docs\//, "");
  h = h.replace(/\.md($|#)/, "$1");
  if (h === "README" || h === "") return "/";
  return "/" + h;
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

const COMPONENTS = {
  a: MdLink,
  table: (props) => (
    <div className="md-table-wrap">
      <table {...props} />
    </div>
  ),
};

export default function MarkdownPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { hash } = useLocation();
  const section = sectionBySlug(slug);

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
          <button className="md-linklike" onClick={() => navigate("/getting-started")}>
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
          components={COMPONENTS}
        >
          {section.body}
        </ReactMarkdown>
      </article>

      <nav className="md-pager">
        {prev ? (
          <Link className="md-pager__btn" to={`/${prev.slug}`}>
            <Icon data={ArrowLeft} size={15} />
            <span>
              <span className="md-pager__dir">Previous</span>
              <span className="md-pager__title">{prev.title}</span>
            </span>
          </Link>
        ) : (
          <span />
        )}
        {next && (
          <Link className="md-pager__btn md-pager__btn_next" to={`/${next.slug}`}>
            <span>
              <span className="md-pager__dir">Next</span>
              <span className="md-pager__title">{next.title}</span>
            </span>
            <Icon data={ArrowRight} size={15} />
          </Link>
        )}
      </nav>
    </>
  );
}
