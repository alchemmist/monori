import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { groupBy, mutationDiagnostics } from "./mutation-diff-report.mjs";

test("identifies affected files and actionable mutants", () => {
    const content = mutationDiagnostics([
        {
            status: "Survived",
            sourcePath: "web/src/example.ts",
            mutatorName: "BooleanLiteral",
            replacement: "true",
            location: { start: { line: 1 } },
        },
        {
            status: "NoCoverage",
            sourcePath: "web/src/example.ts",
            mutatorName: "StringLiteral",
            replacement: '""',
            location: { start: { line: 2 } },
        },
    ]).join("\n");

    assert.match(content, /### Affected files/);
    assert.match(content, /`web\/src\/example\.ts` \| 1 \| 1/);
    assert.match(content, /### Surviving mutants/);
    assert.match(content, /`web\/src\/example\.ts:1` \| BooleanLiteral \| `true`/);
    assert.match(content, /### Mutants without coverage/);
    assert.match(content, /`web\/src\/example\.ts:2` \| StringLiteral \| `""`/);
});

test("groups without relying on newer Node runtimes", () => {
    assert.deepEqual(
        groupBy(["a", "bb", "c"], (value) => String(value.length)),
        {
            1: ["a", "c"],
            2: ["bb"],
        },
    );
});

test("preserves literal backticks with a longer code-span delimiter", () => {
    const content = mutationDiagnostics([
        {
            status: "Survived",
            sourcePath: "web/src/example.ts",
            mutatorName: "StringLiteral",
            replacement: "a`b``c",
            location: { start: { line: 3 } },
        },
    ]).join("\n");

    assert.match(content, /```a`b``c```/);
});

function mutationGateResult(killed, survived, threshold) {
    const directory = mkdtempSync(join(tmpdir(), "mutation-diff-gate-"));
    const source = join(directory, "web/src/example.ts");
    mkdirSync(join(directory, "web/src"), { recursive: true });
    execFileSync("git", ["init", "--quiet"], { cwd: directory });
    execFileSync("git", ["config", "user.email", "test@example.com"], { cwd: directory });
    execFileSync("git", ["config", "user.name", "Test"], { cwd: directory });
    writeFileSync(source, "export const value = false;\n");
    execFileSync("git", ["add", "."], { cwd: directory });
    execFileSync("git", ["commit", "--quiet", "-m", "base"], { cwd: directory });
    const base = execFileSync("git", ["rev-parse", "HEAD"], {
        cwd: directory,
        encoding: "utf8",
    }).trim();
    writeFileSync(source, "export const value = true;\n");
    execFileSync("git", ["add", "."], { cwd: directory });
    execFileSync("git", ["commit", "--quiet", "-m", "change"], { cwd: directory });
    const mutants = [
        ...Array.from({ length: killed }, () => ({
            status: "Killed",
            location: { start: { line: 1 } },
        })),
        ...Array.from({ length: survived }, () => ({
            status: "Survived",
            location: { start: { line: 1 } },
        })),
    ];
    const report = join(directory, "report.json");
    writeFileSync(report, JSON.stringify({ files: { "src/example.ts": { mutants } } }));
    return spawnSync(
        process.execPath,
        [
            new URL("./mutation-diff-gate.mjs", import.meta.url).pathname,
            base,
            report,
            `${threshold}`,
        ],
        { cwd: directory, encoding: "utf8" },
    );
}

test("mutation diff score passes with survivors above the threshold", () => {
    const result = mutationGateResult(466, 162, 60);

    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /score\s+74\.20%/);
    assert.match(result.stdout, /survived\s+162/);
});

test("mutation diff score fails below the threshold", () => {
    const result = mutationGateResult(59, 41, 60);

    assert.equal(result.status, 1);
    assert.match(result.stdout, /score\s+59\.00%/);
});
