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
    const longMerchant = "АВИАБИЛЕТЫ В КРУГОСВЕТНЫХ ПУТЕШЕСТВИЯХ";
    const longMerchantLabel = "АВИАБИЛЕТЫ В КРУГОСВЕТНЫХ";
    await user.api.addTransaction({
        accountId,
        categoryId: foodCat,
        amount: -50000,
        description: longMerchant,
    });

    await openApp(page, user);
    await gotoSection(page, "Dashboard");

    const cash = page.locator(".balance-card", { hasText: "Cash" });
    await expect(cash.locator(".balance-card__value")).toContainText("150");

    const spent = page.locator(".kpi", { hasText: "Spent this month" });
    await expect(spent.locator(".kpi__value")).toContainText("750");

    await expect(page.locator(".chart-card").first()).toBeVisible();
    expect(await page.locator(".chart-card").count()).toBeGreaterThan(2);

    const merchantsCard = page.locator(".chart-card", { hasText: "Top merchants" });
    const longTick = merchantsCard.locator(`.merchant-tick[title="${longMerchantLabel}"]`);
    await longTick.scrollIntoViewIfNeeded();
    await expect(longTick).toBeVisible();

    const expectTickInsideCard = async () => {
        const [cardBox, tickBox] = await Promise.all([
            merchantsCard.boundingBox(),
            longTick.boundingBox(),
        ]);
        expect(tickBox.x).toBeGreaterThanOrEqual(cardBox.x);
        expect(tickBox.x + tickBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width);
        expect(
            await longTick.evaluate((el) => {
                const style = getComputedStyle(el);
                return [style.overflow, style.whiteSpace];
            }),
        ).toEqual(["hidden", "nowrap"]);
    };

    await expectTickInsideCard();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(longTick).toBeVisible();
    await expectTickInsideCard();
});
