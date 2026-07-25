import { test, expect, openApp, gotoSection } from "./fixtures/fixtures.js";

test("dashboard shows the seeded balances, KPIs and charts", async ({ page, user }) => {
    const snap = await user.api.snapshot();
    const accountId = snap.accounts[0].id;
    const { id: incomeGid } = await user.api.createGroup("Earnings", "income");
    const { id: wageCat } = await user.api.createCategory("Wages", incomeGid);
    const { id: gid } = await user.api.createGroup("Spending");
    const { id: foodCat } = await user.api.createCategory("Food", gid);
    // amounts stay under 1 000 ₽ so the assertions dodge locale group separators
    await user.api.addTransaction({
        accountId,
        categoryId: wageCat,
        amount: 90000,
        description: "SALARY",
    });
    await user.api.addTransaction({
        accountId,
        categoryId: foodCat,
        amount: -25000,
        description: "GROCERY STORE",
    });

    await openApp(page, user);
    await gotoSection(page, "Dashboard");

    const cash = page.locator(".balance-card", { hasText: "Cash" });
    await expect(cash.locator(".balance-card__value")).toContainText("650");

    const spent = page.locator(".kpi", { hasText: "Spent this month" });
    await expect(spent.locator(".kpi__value")).toContainText("250");

    await expect(page.locator(".chart-card").first()).toBeVisible();
    expect(await page.locator(".chart-card").count()).toBeGreaterThan(2);
});
