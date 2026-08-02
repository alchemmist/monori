import AxeBuilder from "@axe-core/playwright";
import { test, expect, gotoSection, openApp } from "./fixtures/fixtures.js";

const SECTIONS = [
    "Budget",
    "Dashboard",
    "Transactions",
    "Accounts",
    "Categories",
    "Settings",
] as const;

test("reports accessibility violations on authenticated sections", async ({
    page,
    user,
}, testInfo) => {
    await openApp(page, user);

    const report: Record<string, unknown> = {};
    const violations: string[] = [];
    for (const section of SECTIONS) {
        if (section !== "Budget") {
            await gotoSection(page, section);
        }
        await expect(page.locator("h1")).toBeVisible();

        const results = await new AxeBuilder({ page }).analyze();
        report[section] = results.violations;
        violations.push(
            ...results.violations
                .filter(
                    (violation) =>
                        violation.impact === "critical" || violation.impact === "serious",
                )
                .map(
                    (violation) => `${section}: ${violation.id} (${violation.impact ?? "unknown"})`,
                ),
        );
        console.log(
            `[a11y] ${section}: ${results.violations.length} violation(s), ` +
                `${results.incomplete.length} incomplete check(s)`,
        );
        for (const violation of results.violations) {
            console.log(
                `[a11y] ${section} ${violation.id} (${violation.impact ?? "unknown"}): ` +
                    `${violation.help} — ${violation.nodes.length} node(s)`,
            );
            for (const node of violation.nodes) {
                console.log(`[a11y]   target: ${node.target.join(", ")}`);
            }
        }
    }

    await testInfo.attach("accessibility-report.json", {
        body: JSON.stringify(report, null, 2),
        contentType: "application/json",
    });
    expect(Object.keys(report)).toHaveLength(SECTIONS.length);
    expect(violations, `Accessibility violations found:\n${violations.join("\n")}`).toHaveLength(0);
});
