function markdownCode(value) {
    const content = String(value ?? "")
        .replaceAll("|", "\\|")
        .replaceAll("\n", " ");
    const maxBacktickRun = Math.max(0, ...(content.match(/`+/g) ?? []).map((run) => run.length));
    const delimiter = "`".repeat(maxBacktickRun + 1);
    return `${delimiter}${content}${delimiter}`;
}

export function groupBy(items, keyFor) {
    const groups = {};
    for (const item of items) {
        const key = keyFor(item);
        (groups[key] ??= []).push(item);
    }
    return groups;
}

function findingRows(items) {
    return items.map((mutant) => {
        const line = mutant.location?.start?.line ?? "?";
        return `| ${markdownCode(`${mutant.sourcePath}:${line}`)} | ${mutant.mutatorName ?? "Unknown"} | ${markdownCode(mutant.replacement)} |`;
    });
}

export function mutationDiagnostics(findings) {
    if (findings.length === 0) return [];
    const affectedFiles = groupBy(findings, (mutant) => mutant.sourcePath);
    const diagnostics = [
        "",
        "### Affected files",
        "",
        "| File | Survived | No coverage |",
        "| --- | ---: | ---: |",
    ];
    for (const [path, items] of Object.entries(affectedFiles).sort(([a], [b]) =>
        a.localeCompare(b),
    )) {
        diagnostics.push(
            `| ${markdownCode(path)} | ${items.filter((item) => item.status === "Survived").length} | ${items.filter((item) => item.status === "NoCoverage").length} |`,
        );
    }
    const survivingMutants = findings.filter((mutant) => mutant.status === "Survived");
    if (survivingMutants.length > 0) {
        diagnostics.push(
            "",
            "### Surviving mutants",
            "",
            "| Location | Mutator | Replacement |",
            "| --- | --- | --- |",
            ...findingRows(survivingMutants),
        );
    }
    const uncoveredMutants = findings.filter((mutant) => mutant.status === "NoCoverage");
    if (uncoveredMutants.length > 0) {
        diagnostics.push(
            "",
            "### Mutants without coverage",
            "",
            "| Location | Mutator | Replacement |",
            "| --- | --- | --- |",
            ...findingRows(uncoveredMutants),
        );
    }
    return diagnostics;
}
