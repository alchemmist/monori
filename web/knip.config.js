export default {
    project: ["src/**/*.{ts,tsx}", "e2e/**/*.ts", "*.{config,conf}.ts"],
    entry: ["src/main.tsx", "e2e/**/*.spec.ts", "e2e/fixtures/fixtures.ts", "*.{config,conf}.ts"],
    // These packages are invoked by Makefile/CI commands or imported from CSS,
    // so Knip cannot discover their usage from the TypeScript module graph.
    ignoreDependencies: [
        "@fontsource/inter",
        "@stryker-mutator/core",
        "@stryker-mutator/vitest-runner",
        "htmlhint",
        "markdownlint-cli2",
        "oxlint",
        "oxlint-tsgolint",
        "prettier",
    ],
};
