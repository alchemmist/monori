import { execFileSync } from "node:child_process";
import fs from "node:fs";
import process from "node:process";

const [base, reportPath, thresholdText] = process.argv.slice(2);
const threshold = Number(thresholdText);
if (!base || !reportPath || !Number.isFinite(threshold)) {
    console.error("usage: mutation-diff-gate.mjs <base> <reportPath> <threshold>");
    process.exit(2);
}

function parseChangedLines(diff) {
    const paths = new Map();
    let current = null;
    let newLine = 0;
    let deletionOnly = false;
    for (const line of diff.split("\n")) {
        if (line === "\\ No newline at end of file") {
            continue;
        } else if (line.startsWith("+++ ")) {
            const target = line.slice(4);
            current = target === "/dev/null" ? null : normalizePath(target);
            if (current) paths.set(current, new Set());
        } else if (line.startsWith("@@")) {
            const match = line.match(/\+(\d+)(?:,(\d+))?/);
            if (!match) continue;
            newLine = Number(match[1]);
            deletionOnly = match[2] === "0";
        } else if (current && line.startsWith("+") && !line.startsWith("+++")) {
            paths.get(current).add(newLine);
            newLine += 1;
        } else if (current && line.startsWith("-") && !line.startsWith("---")) {
            paths.get(current).add(Math.max(1, deletionOnly ? newLine : newLine - 1));
        } else if (current && newLine) {
            newLine += 1;
        }
    }
    return paths;
}

function normalizePath(path) {
    return path.replace(/^b\//, "").replace(/^web\//, "");
}

const changedLines = parseChangedLines(
    execFileSync("git", ["diff", "--unified=0", `${base}...HEAD`, "--", "web/src"], {
        encoding: "utf8",
    }),
);
const changedFiles = new Set(changedLines.keys());

if (changedFiles.size === 0) {
    console.log("mutation-diff: no changed frontend files — pass");
    process.exit(0);
}

if (!fs.existsSync(reportPath)) {
    console.log("mutation-diff: no Stryker report for changed frontend files — pass");
    process.exit(0);
}

const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
const mutants = Object.entries(report.files ?? {})
    .filter(([path]) => changedFiles.has(normalizePath(path)))
    .flatMap(([path, file]) =>
        (file.mutants ?? []).filter((mutant) => {
            const lines = changedLines.get(normalizePath(path));
            const line = mutant.location?.start?.line;
            return line === undefined || lines.has(line);
        }),
    );
const counts = Object.groupBy(mutants, (mutant) => mutant.status);
const killed = counts.Killed?.length ?? 0;
const timedOut = counts.Timeout?.length ?? 0;
const survived = counts.Survived?.length ?? 0;
const other = ["NoCoverage"].reduce((total, status) => total + (counts[status]?.length ?? 0), 0);
const detected = killed + timedOut;
const considered = detected + survived + other;

if (considered === 0) {
    console.log("mutation-diff: changed frontend files have no tested mutants — pass");
    process.exit(0);
}

const score = (detected * 100) / considered;
const passed = score >= threshold && survived === 0;
console.log("── changed frontend mutation summary ────────────────");
console.log(`killed             ${killed}`);
console.log(`survived           ${survived}`);
console.log(`considered         ${considered}`);
console.log(`score              ${score.toFixed(2)}%`);
console.log(`threshold          ${threshold}%`);
console.log(`mutation-diff gate ${passed ? "PASS" : "FAIL"}`);
process.exit(passed ? 0 : 1);
