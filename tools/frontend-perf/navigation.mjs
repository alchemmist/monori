import fs from "node:fs/promises";
import { chromium } from "@playwright/test";
import config from "./config.json" with { type: "json" };

const [tokenFile, outputFile] = process.argv.slice(2);
const baseURL = process.env.PERF_BASE_URL;

if (!tokenFile || !outputFile) {
    throw new Error("usage: node navigation.mjs TOKEN_FILE OUTPUT_FILE");
}
if (!baseURL) throw new Error("PERF_BASE_URL is required");

const { token } = JSON.parse(await fs.readFile(tokenFile, "utf8"));
if (typeof token !== "string" || token === "") throw new Error("perf token is missing");

const browser = await chromium.launch();
const results = [];

try {
    for (const scenario of config.navigationScenarios) {
        const valuesMs = [];
        for (let run = 0; run < config.runs; run += 1) {
            const context = await browser.newContext({ viewport: { width: 1600, height: 900 } });
            const page = await context.newPage();
            await page.addInitScript((accessToken) => {
                localStorage.setItem("monori_token", accessToken);
            }, token);
            await page.goto(new URL(scenario.startPath, baseURL).toString());
            await page.locator(".year-grid").waitFor({ timeout: 90000 });

            await page.evaluate(() => performance.mark("monori-perf-navigation-start"));
            if (scenario.action === "month") {
                await page.getByText("Month", { exact: true }).last().click();
            } else {
                await page.locator(".sidebar__item", { hasText: scenario.action }).first().click();
            }
            await page.locator(scenario.readySelector).waitFor({ timeout: 90000 });
            await page.evaluate(
                () =>
                    new Promise((resolve) => {
                        requestAnimationFrame(() => requestAnimationFrame(resolve));
                    }),
            );
            const duration = await page.evaluate(() => {
                performance.mark("monori-perf-navigation-end");
                return performance.measure(
                    "monori-perf-navigation",
                    "monori-perf-navigation-start",
                    "monori-perf-navigation-end",
                ).duration;
            });
            valuesMs.push(duration);
            await context.close();
        }
        results.push({ id: scenario.id, label: scenario.label, valuesMs });
    }
} finally {
    await browser.close();
}

await fs.writeFile(outputFile, JSON.stringify({ scenarios: results }, null, 2) + "\n");
