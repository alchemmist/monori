import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const here = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            "/api":
                process.env["MONORI_API"] ?? `http://localhost:${process.env["API_PORT"] ?? 8077}`,
        },
        // serve web/ plus ../docs only (the docs pages read markdown from
        // ../docs via import.meta.glob) — not the whole repo root
        fs: { allow: [here, path.resolve(here, "..", "docs")] },
        ...(process.env["VITE_FORCE_POLLING"]
            ? { watch: { usePolling: true, interval: 500 } }
            : {}),
    },
    test: {
        // e2e/ holds Playwright specs with their own runner — vitest must not
        // pick them up
        include: ["src/**/*.{test,spec}.{ts,tsx}"],
        // component tests render into jsdom; the pure-logic suites don't care
        environment: "jsdom",
        setupFiles: ["src/test/setup.ts"],
        execArgv: ["--disable-warning=ExperimentalWarning"],
        // component tests wait on real DOM updates; the default 5s holds
        // locally but not under v8 instrumentation on a loaded runner, where
        // a lazy route plus the demo dataset can take tens of seconds to mount
        testTimeout: 30000,
        coverage: {
            provider: "v8",
            include: ["src/**/*.{ts,tsx}"],
            exclude: [
                "src/**/*.test.{ts,tsx}",
                "src/main.tsx",
                "src/test/**",
                // decorative-only: generative canvas art whose every frame lands
                // on a 2d context jsdom does not implement, so nothing a DOM
                // assertion could reach ever happens (Wordmark is plain markup
                // and stays in — it is covered like any other component)
                "src/components/Meadow.tsx",
                "src/components/GlyphFlower.tsx",
            ],
            reporter: ["text", "json-summary"],
            reportsDirectory: "./coverage",
            // the global gate is what stops coverage leaking away between
            // features; the engine keeps its own line so the budgeting math
            // cannot be diluted by cheaply-covered UI
            thresholds: {
                lines: 90,
                statements: 90,
                "src/engine/**": { lines: 90, statements: 90 },
            },
        },
    },
});
