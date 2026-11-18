import assert from "node:assert/strict";
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
