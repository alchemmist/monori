import { execFileSync } from "node:child_process";
import fs from "node:fs";
import process from "node:process";

const [base, reportPath, thresholdText] = process.argv.slice(2);
const threshold = Number(thresholdText);
const changedFiles = new Set(
    execFileSync("git", ["diff", "--name-only", `${base}...HEAD`, "--", "web/src"], {
        encoding: "utf8",
    })
        .trim()
        .split("\n")
        .filter(Boolean)
        .map((path) => path.replace(/^web\//, "")),
);

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
    .filter(([path]) => changedFiles.has(path.replace(/^web\//, "")))
    .flatMap(([, file]) => file.mutants ?? []);
const counts = Object.groupBy(mutants, (mutant) => mutant.status);
const killed = counts.Killed?.length ?? 0;
const survived = counts.Survived?.length ?? 0;
const other = ["NoCoverage", "Timeout", "RuntimeError"].reduce(
    (total, status) => total + (counts[status]?.length ?? 0),
    0,
);
const considered = killed + survived + other;

if (considered === 0) {
    console.log("mutation-diff: changed frontend files have no tested mutants — pass");
    process.exit(0);
}

const score = (killed * 100) / considered;
const passed = score >= threshold && survived === 0;
console.log("── changed frontend mutation summary ────────────────");
console.log(`killed             ${killed}`);
console.log(`survived           ${survived}`);
console.log(`considered         ${considered}`);
console.log(`score              ${score.toFixed(2)}%`);
console.log(`threshold          ${threshold}%`);
console.log(`mutation-diff gate ${passed ? "PASS" : "FAIL"}`);
process.exit(passed ? 0 : 1);
