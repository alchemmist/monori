const raw = import.meta.glob("../../docs/*.md", {
    query: "?raw",
    import: "default",
    eager: true,
});

function md(name) {
    return raw[`../../docs/${name}.md`] ?? "";
}

export const NAV = [
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

export function sectionBySlug(slug) {
    return SECTIONS.find((s) => s.slug === slug);
}

export function neighbors(slug) {
    const i = SECTIONS.findIndex((s) => s.slug === slug);
    return {
        prev: i > 0 ? SECTIONS[i - 1] : null,
        next: i >= 0 && i < SECTIONS.length - 1 ? SECTIONS[i + 1] : null,
    };
}
