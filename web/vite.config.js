import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const here = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            "/api": process.env.MONORI_API ?? `http://localhost:${process.env.API_PORT ?? 8077}`,
        },
        // serve web/ plus ../docs only (the docs pages read markdown from
        // ../docs via import.meta.glob) — not the whole repo root
        fs: { allow: [here, path.resolve(here, "..", "docs")] },
        watch: process.env.VITE_FORCE_POLLING ? { usePolling: true, interval: 500 } : undefined,
    },
    test: {
        // e2e/ holds Playwright specs with their own runner — vitest must not
        // pick them up
        include: ["src/**/*.{test,spec}.{js,jsx}"],
        // component tests render into jsdom; the pure-logic suites don't care
        environment: "jsdom",
        setupFiles: ["src/test/setup.js"],
        coverage: {
            provider: "v8",
            all: true,
            include: ["src/**/*.{js,jsx}"],
            exclude: [
                "src/**/*.test.{js,jsx}",
                "src/main.jsx",
                "src/test/**",
                // decorative-only: generative canvas/SVG art with no behavior a
                // DOM assertion could pin down (jsdom paints nothing anyway)
                "src/components/Meadow.jsx",
                "src/components/GlyphFlower.jsx",
                "src/components/Wordmark.jsx",
            ],
            reporter: ["text", "json-summary"],
            reportsDirectory: "./coverage",
            // the global gate is what stops coverage leaking away between
            // features; the engine keeps its own line so the budgeting math
            // cannot be diluted by cheaply-covered UI
            thresholds: {
                lines: 80,
                statements: 80,
                "src/engine/**": { lines: 80, statements: 80 },
            },
        },
    },
});
