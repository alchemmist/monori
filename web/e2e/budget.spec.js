import { test, expect, openApp, YEAR, MONTH } from "./fixtures/fixtures.js";

// June's "Bud" cell in the year grid: td 0 is the category name, then one td
// per month in "Plan" density.
const juneCell = (row) => row.locator("td").nth(MONTH);

test("editing a budgeted cell recomputes available-to-budget and persists", async ({
    page,
    user,
}) => {
    const { id: gid } = await user.api.createGroup("Essentials");
    await user.api.createCategory("Groceries", gid);

    await openApp(page, user);
    // "Plan" density leaves only the Budgeted column per month, so cell
    // positions are stable to address
    await page.getByText("Plan", { exact: true }).click();

    const row = page.locator(".yg-row", { hasText: "Groceries" });
    const june = page.locator(".yg-msum").nth(MONTH - 1);
    await expect(row).toBeVisible();
    await expect(june.locator(".yg-msum__av")).toHaveText("0 ₽");

    await juneCell(row).locator(".budget-cell").click();
    await juneCell(row).locator(".budget-cell__input").fill("500");
    await page.keyboard.press("Enter");

    // nothing funds the budget, so budgeting 500 drives June negative — the
    // whole header band recomputed in the same frame
    await expect(juneCell(row)).toHaveText("500");
    await expect(june.locator(".yg-msum__av")).toHaveText("-500 ₽");

    await page.reload();
    await expect(page.locator(".sidebar")).toBeVisible();
    await page.getByText("Plan", { exact: true }).click();
    await expect(juneCell(page.locator(".yg-row", { hasText: "Groceries" }))).toHaveText("500");
    await expect(
        page
            .locator(".yg-msum")
            .nth(MONTH - 1)
            .locator(".yg-msum__av"),
    ).toHaveText("-500 ₽");
});

test("activity and balance reflect seeded transactions", async ({ page, user }) => {
    const snap = await user.api.snapshot();
    const accountId = snap.accounts[0].id;
    const { id: gid } = await user.api.createGroup("Life");
    const { id: cid } = await user.api.createCategory("Cafe", gid);
    await user.api.setBudget(cid, YEAR, MONTH, 30000);
    await user.api.addTransaction({
        accountId,
        categoryId: cid,
        amount: -20000,
        description: "COFFEE SPOT",
    });

    await openApp(page, user);
    const row = page.locator(".yg-row", { hasText: "Cafe" });
    // full density: per month td offset 1 + (m-1)*3 → June Bud/Act/Bal
    const base = 1 + (MONTH - 1) * 3;
    await expect(row.locator("td").nth(base)).toHaveText("300");
    await expect(row.locator("td").nth(base + 1)).toHaveText("-200");
    await expect(row.locator("td").nth(base + 2)).toHaveText("100");
});
