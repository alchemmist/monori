import fs from "node:fs/promises";
import path from "node:path";
import config from "./config.json" with { type: "json" };

const [lighthouseDir, navigationFile, outputDir] = process.argv.slice(2);
if (!lighthouseDir || !navigationFile || !outputDir) {
    throw new Error("usage: node baseline.mjs LIGHTHOUSE_DIR NAVIGATION_FILE OUTPUT_DIR");
}

const median = (values) => {
    const sorted = [...values].sort((left, right) => left - right);
    return sorted[Math.floor(sorted.length / 2)];
};

const files = (await fs.readdir(lighthouseDir)).filter((name) => name.endsWith(".json"));
const reports = await Promise.all(
    files.map(async (name) =>
        JSON.parse(await fs.readFile(path.join(lighthouseDir, name), "utf8")),
    ),
);
const metrics = Object.entries(config.metrics).filter(([id]) => id !== "navigation");
const targets = {
    "largest-contentful-paint": 2500,
    "total-blocking-time": 300,
    "cumulative-layout-shift": 0.1,
};
const reportedMetrics = [
    ["interactive", "TTI", "ms"],
    ["mainthread-work-breakdown", "Main thread", "ms"],
];
const rows = [];
for (const route of config.lighthouseRoutes) {
    const matching = reports.filter((report) => new URL(report.finalUrl).pathname === route.path);
    for (const [metricId, policy] of metrics) {
        const values = matching.map((report) => Number(report.audits[metricId].numericValue));
        if (values.length === 0) continue;
        const measured = median(values);
        const target = route.sla?.[metricId] ?? targets[metricId] ?? policy.good;
        rows.push({
            route: route.label,
            metric: policy.label,
            value: measured,
            target,
            unit: policy.unit,
            passed: measured <= target,
        });
    }
    for (const [metricId, label, unit] of reportedMetrics) {
        const values = matching
            .map((report) => Number(report.audits[metricId]?.numericValue))
            .filter(Number.isFinite);
        if (values.length === 0) continue;
        rows.push({
            route: route.label,
            metric: label,
            value: median(values),
            target: null,
            unit,
            passed: null,
        });
    }
}

const navigation = JSON.parse(await fs.readFile(navigationFile, "utf8"));
for (const scenario of config.navigationScenarios) {
    const values = navigation.scenarios.find((item) => item.id === scenario.id)?.valuesMs || [];
    if (values.length === 0) continue;
    const measured = median(values.map(Number));
    rows.push({
        route: scenario.label,
        metric: "Interaction",
        value: measured,
        target: null,
        unit: "ms",
        passed: null,
    });
}

const report = {
    passed: rows.filter((row) => row.target !== null).every((row) => row.passed),
    rows,
};
await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(path.join(outputDir, "frontend.json"), `${JSON.stringify(report, null, 2)}\n`);
const markdown = [
    "# Frontend performance summary",
    "",
    "| Route | Metric | Measured | Target | Verdict |",
    "| --- | --- | ---: | ---: | --- |",
    ...rows.map(
        (row) =>
            `| ${row.route} | ${row.metric} | ${row.value.toFixed(row.unit === "score" ? 3 : 0)} ${row.unit} | ${row.target === null ? "report only" : `≤ ${row.target} ${row.unit}`} | ${row.target === null ? "measured" : row.passed ? "pass" : "fail"} |`,
    ),
    "",
].join("\n");
await fs.writeFile(path.join(outputDir, "frontend.md"), markdown);
if (!report.passed) process.exitCode = 1;
