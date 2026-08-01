import { defineConfig, devices } from "@playwright/test";

// e2e against the real stack from deploy/docker-compose.test.yml — run it via
// `make t-slow` (which brings the stack up and tears it down), or point
// E2E_BASE_URL at an already-running stack and `npx playwright test` directly.
export default defineConfig({
    testDir: "e2e",
    fullyParallel: true,
    forbidOnly: !!process.env["CI"],
    retries: process.env["CI"] ? 2 : 0,
    reporter: process.env["CI"] ? [["list"], ["html", { open: "never" }]] : [["list"]],
    use: {
        baseURL: process.env["E2E_BASE_URL"] ?? "http://localhost:8078",
        trace: "on-first-retry",
        screenshot: "only-on-failure",
    },
    projects: [
        {
            name: "chromium",
            use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 900 } },
        },
    ],
});
