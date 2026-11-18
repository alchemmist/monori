// Stryker disable all: vite resolves this glob at build time, so every argument
// has to stay a literal — an instrumented one fails to parse at all
const raw = import.meta.glob<string>("../../docs/*.md", {
    query: "?raw",
    import: "default",
    eager: true,
});
// Stryker restore all

// react-markdown 9 has no raw-HTML pass, so an HTML comment reaches the page as
// literal text; the docs use them as generator markers, so drop them here.
// Loops to a fixpoint: a single pass over "<!<!---->--…-->" leaves a comment
export function stripHtmlComments(text: string) {
    let out = text;
    let prev;
    do {
        prev = out;
        out = out.replace(/<!--[\s\S]*?-->[ \t]*\n?/g, "");
    } while (out !== prev);
    return out;
}

function md(name: string) {
    return stripHtmlComments(raw[`../../docs/${name}.md`] ?? "");
}

export interface ContentSection {
    slug: string;
    title: string;
    body: string;
}

export const NAV: Array<{ group: string; items: ContentSection[] }> = [
    {
        group: "Start here",
        items: [{ slug: "getting-started", title: "Getting started", body: md("getting-started") }],
    },
    {
        group: "Using monori",
        items: [
            { slug: "budgeting", title: "Budgeting", body: md("budgeting") },
            { slug: "transactions", title: "Transactions", body: md("transactions") },
            { slug: "accounts", title: "Accounts & transfers", body: md("accounts") },
            { slug: "importing", title: "Importing statements", body: md("importing") },
            { slug: "migration", title: "Migrating from a spreadsheet", body: md("migration") },
            {
                slug: "dashboard-analytics",
                title: "Dashboard & analytics",
                body: md("dashboard-analytics"),
            },
        ],
    },
    {
        group: "Self-hosting",
        items: [{ slug: "configuration", title: "Configuration", body: md("configuration") }],
    },
    {
        group: "Reference",
        items: [
            { slug: "api", title: "REST API", body: md("api") },
            { slug: "data-model", title: "Data model", body: md("data-model") },
        ],
    },
    {
        group: "Contributing",
        items: [{ slug: "development", title: "Development", body: md("development") }],
    },
];

export const SECTIONS = NAV.flatMap((g) => g.items);

// the fullscreen viewer addresses a diagram by its position on the page, so the
// page and the viewer have to extract the fences the same way
export function mermaidCharts(body?: string) {
    return [...String(body ?? "").matchAll(/```mermaid[^\n]*\n([\s\S]*?)```/g)].map((m) =>
        m[1]!.replace(/\n$/, ""),
    );
}

export function sectionBySlug(slug: string) {
    return SECTIONS.find((s) => s.slug === slug);
}

export function neighbors(slug: string) {
    const i = SECTIONS.findIndex((s) => s.slug === slug);
    return {
        prev: i > 0 ? SECTIONS[i - 1] : null,
        next: i >= 0 && i < SECTIONS.length - 1 ? SECTIONS[i + 1] : null,
    };
}
