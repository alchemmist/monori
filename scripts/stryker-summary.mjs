import fs from "node:fs";

const reportPath = process.argv[2] ?? "web/reports/stryker-incremental.json";

if (!fs.existsSync(reportPath)) {
    console.log("── stryker result: report was not written ──");
    process.exit(0);
}

const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
const statuses = {};

for (const file of Object.values(report.files ?? {})) {
    for (const mutant of file.mutants ?? []) {
        statuses[mutant.status] = (statuses[mutant.status] ?? 0) + 1;
    }
}

const killed = statuses.Killed ?? 0;
const denominator = ["Killed", "Survived", "NoCoverage", "Timeout", "RuntimeError"].reduce(
    (total, status) => total + (statuses[status] ?? 0),
    0,
);
const score = denominator ? ((killed * 100) / denominator).toFixed(2) : "n/a";

console.log(
    `── stryker result: ${score}% (killed ${killed}, survived ${statuses.Survived ?? 0}, no coverage ${statuses.NoCoverage ?? 0}, timeout ${statuses.Timeout ?? 0}, runtime error ${statuses.RuntimeError ?? 0}) ──`,
);
