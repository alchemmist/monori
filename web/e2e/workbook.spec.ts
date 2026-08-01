import { fileURLToPath } from "node:url";
import type { Page, TestInfo } from "@playwright/test";
import type { Snapshot } from "../src/types.js";
import {
    test,
    expect,
    openApp,
    gotoSection,
    switchUser,
    makeUser,
    YEAR,
    MONTH,
} from "./fixtures/fixtures.js";

// seed dates hang off the pinned clock: month m (1-based), day d, noon
const date = (month: number, day: number) =>
    `${YEAR}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}T12:00:00`;

const FIXTURE = fileURLToPath(new URL("./fixtures/template-workbook.xlsx", import.meta.url));

// Everything the workbook round-trip guarantees, keyed by names instead of
// ids so two different tenants can be compared. Order matters for groups
// (kanban order survives the trip); the rest is sorted.
function comparable(snap: Snapshot) {
    const accName = new Map(snap.accounts.map((a) => [a.id, a.name]));
    const catName = new Map(snap.categories.map((c) => [c.id, c.name]));
    const grpName = new Map(snap.groups.map((g) => [g.id, g.name]));
    const byJson = (a: unknown, b: unknown) => JSON.stringify(a).localeCompare(JSON.stringify(b));
    return {
        groups: snap.groups.map((g) => ({ name: g.name, kind: g.kind })),
        categories: snap.categories
            .map((c) => ({
                name: c.name,
                group: grpName.get(c.groupId),
                keywords: c.keywords,
            }))
            .sort(byJson),
        transactions: snap.transactions
            .map((t) => ({
                date: t.date.slice(0, 10),
                amount: t.amount,
                description: t.description,
                category: t.categoryId == null ? null : catName.get(t.categoryId),
                account: accName.get(t.accountId),
            }))
            .sort(byJson),
        budgets: snap.budgets
            .map((b) => ({
                category: catName.get(b.categoryId),
                year: b.year,
                month: b.month,
                amount: b.amount,
            }))
            .sort(byJson),
    };
}

// Drive the whole migration tab: pick the file, wait for the preview, map
// every account marker via mapAccount(marker) -> account name, import, and
// return the result summary text. Closes the tab afterwards.
async function migrate(page: Page, filePath: string, mapAccount: (marker: string) => string) {
    await gotoSection(page, "Settings");
    await page.getByRole("button", { name: "Migrate from spreadsheet" }).click();
    const tab = page.locator(".ui-tab", { hasText: "Migrate from spreadsheet" });
    await tab.locator('input[type="file"]').setInputFiles(filePath);
    await expect(tab.getByText(/groups, \d+ categories, \d+ transactions/)).toBeVisible();

    const selects = tab.locator(".gsel_field");
    const count = await selects.count();
    for (let i = 0; i < count; i++) {
        const sel = selects.nth(i);
        const label = (await sel.locator(".gsel__label").textContent()) ?? "";
        expect(label, "account marker label").toMatch(/^Account for /);
        const marker = label.replace(/^Account for\s*/, "");
        await sel.click();
        await page
            .locator(".gsel__drop")
            .getByRole("option", { name: mapAccount(marker), exact: true })
            .click();
    }

    await tab.getByRole("button", { name: "Import" }).click();
    const result = tab.getByText(/^Imported \d+ transactions/);
    await expect(result).toBeVisible();
    const text = await result.textContent();
    await tab.getByRole("button", { name: "Done" }).click();
    return text;
}

// Click Settings -> Export to Excel and save the downloaded workbook to the
// test's own output dir (download.path() may be unavailable in some runners).
async function exportWorkbook(page: Page, testInfo: TestInfo) {
    await gotoSection(page, "Settings");
    const [download] = await Promise.all([
        page.waitForEvent("download"),
        page.getByRole("button", { name: "Export to Excel" }).click(),
    ]);
    expect(download.suggestedFilename()).toBe("monori-export.xlsx");
    const out = testInfo.outputPath("monori-export.xlsx");
    await download.saveAs(out);
    return out;
}

test("monori data survives export and re-import into a fresh account", async ({
    page,
    request,
    user,
}, testInfo) => {
    // world A: two accounts, income + expense groups, keywords, budgets and
    // a mix of categorized/uncategorized transactions
    const { id: cardId } = await user.api.createAccount({ name: "Card" });
    const snapA0 = await user.api.snapshot();
    const cashId = snapA0.accounts.find((a) => a.name === "Cash")!.id;
    const { id: daily } = await user.api.createGroup("Daily");
    const { id: inflow } = await user.api.createGroup("Inflow", "income");
    const { id: groceries } = await user.api.createCategory("Groceries", daily, "lenta|okey");
    const { id: cafe } = await user.api.createCategory("Cafe", daily, "coffee");
    const { id: salary } = await user.api.createCategory("Salary", inflow);
    await user.api.addTransaction({
        accountId: cashId,
        categoryId: salary,
        amount: 90000,
        date: date(MONTH - 1, 5),
        description: "PAYROLL",
    });
    await user.api.addTransaction({
        accountId: cardId,
        categoryId: groceries,
        amount: -12300,
        date: date(MONTH - 1, 15),
        description: "LENTA-101",
    });
    await user.api.addTransaction({
        accountId: cardId,
        categoryId: cafe,
        amount: -4500,
        date: date(MONTH, 2),
        description: "COFFEE POINT",
    });
    await user.api.addTransaction({
        accountId: cashId,
        amount: -700,
        date: date(MONTH, 5),
        description: "MISC SHOP",
    });
    await user.api.setBudget(groceries, YEAR, MONTH - 1, 30000);
    await user.api.setBudget(groceries, YEAR, MONTH, 30000);
    await user.api.setBudget(cafe, YEAR, MONTH, 5000);

    await openApp(page, user);
    const exported = await exportWorkbook(page, testInfo);

    // world B: a brand-new tenant with same-named accounts to map onto
    const userB = await makeUser(request, "wb-b");
    await userB.api.createAccount({ name: "Card" });
    await switchUser(page, userB);
    const result = await migrate(page, exported, (marker) => marker);
    expect(result).toContain("Imported 4 transactions (0 duplicates skipped)");

    const a = comparable(await user.api.snapshot());
    const b = comparable(await userB.api.snapshot());
    // guard against a vacuous deep-equal: the normalized shape must really
    // carry the seeded world before the two tenants are compared
    expect(a.groups).toEqual([
        { name: "Daily", kind: "expense" },
        { name: "Inflow", kind: "income" },
    ]);
    expect(a.transactions).toHaveLength(4);
    expect(a.transactions.map((t) => t.category ?? "").sort()).toEqual([
        "",
        "Cafe",
        "Groceries",
        "Salary",
    ]);
    expect(
        a.transactions.every(
            (t) => t.account != null && t.account !== "" && t.date.startsWith(`${YEAR}-`),
        ),
    ).toBe(true);
    expect(a.budgets).toHaveLength(3);
    expect(b).toEqual(a);
});

test("a template workbook migrates in, exports back out with nothing lost", async ({
    page,
    user,
}, testInfo) => {
    // the fixture is a miniature of the real YNAB-like template: Russian
    // T-Bank headers, keyword side table, a 2026 budget grid, two card markers
    await user.api.createAccount({ name: "Salary card" });
    await openApp(page, user);

    const markerMap: Record<string, string> = { "*1111": "Cash", "*2222": "Salary card" };
    const result = await migrate(page, FIXTURE, (marker) => markerMap[marker]!);
    expect(result).toContain("Imported 5 transactions (0 duplicates skipped)");
    expect(result).toContain("2 groups and 3 categories created");
    expect(result).toContain("3 budget cells written");

    // the imported data is really on the pages, not only in the counters
    await gotoSection(page, "Transactions");
    const row = page.locator(".tx-grid .cat-row", { hasText: "LENTA-101" });
    await expect(row).toBeVisible();
    await expect(row.locator(".gsel").last()).toContainText("Groceries");
    await gotoSection(page, "Budget");
    await expect(page.locator(".yg-row", { hasText: "Groceries" })).toBeVisible();

    // export and feed the export straight back in: every transaction must be
    // recognised as a duplicate and nothing new may appear — that is "the
    // exported file equals the imported data" checked through the product
    const before = comparable(await user.api.snapshot());
    const exported = await exportWorkbook(page, testInfo);
    const again = await migrate(page, exported, (marker) => marker);
    expect(again).toContain("Imported 0 transactions (5 duplicates skipped)");
    expect(again).toContain("0 groups and 0 categories created");

    const after = comparable(await user.api.snapshot());
    expect(after).toEqual(before);
});
