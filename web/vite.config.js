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
        coverage: {
            provider: "v8",
            all: true,
            include: ["src/**/*.{js,jsx}"],
            exclude: ["src/**/*.test.{js,jsx}", "src/main.jsx"],
            reporter: ["text", "json-summary"],
            reportsDirectory: "./coverage",
            thresholds: {
                "src/engine/**": { lines: 80, statements: 80 },
            },
        },
    },
});
