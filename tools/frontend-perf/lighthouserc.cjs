const config = require("./config.json");

const baseUrl = process.env.PERF_BASE_URL;
const chromePath = process.env.PERF_CHROME_PATH;

if (!baseUrl) throw new Error("PERF_BASE_URL is required");
if (!chromePath) throw new Error("PERF_CHROME_PATH is required");

module.exports = {
    ci: {
        collect: {
            url: config.lighthouseRoutes.map(({ path: routePath }) =>
                new URL(routePath, baseUrl).toString(),
            ),
            numberOfRuns: config.runs,
            puppeteerScript: "lhci-auth.cjs",
            puppeteerLaunchOptions: {
                executablePath: chromePath,
                headless: true,
                args: ["--no-sandbox", "--disable-dev-shm-usage"],
            },
            settings: {
                onlyCategories: ["performance"],
                formFactor: "desktop",
                throttlingMethod: "simulate",
                disableStorageReset: true,
                maxWaitForLoad: 90000,
                screenEmulation: {
                    mobile: false,
                    width: 1600,
                    height: 900,
                    deviceScaleFactor: 1,
                    disabled: false,
                },
            },
        },
        upload: {
            target: "filesystem",
            outputDir: ".lighthouseci",
        },
    },
};
