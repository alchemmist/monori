import { test, expect, openApp, gotoSection } from "./fixtures/fixtures.js";

test("categorizing via the grouped picker persists and follows kanban order", async ({
    page,
    user,
}) => {
    const snap = await user.api.snapshot();
    const accountId = snap.accounts[0].id;
    // create Zeta first, Alpha second, then reorder Alpha ahead of Zeta — if
    // the picker sectioned by creation order or alphabet instead of the kanban
    // order, one of the two cases below would catch it
    const { id: zeta } = await user.api.createGroup("Zeta Group");
    const { id: alpha } = await user.api.createGroup("Alpha Group");
    await user.api.createCategory("Coffee", zeta);
    await user.api.createCategory("Books", alpha);
    const allGroups = (await user.api.snapshot()).groups.map((g) => g.id);
    await user.api.reorderGroups([alpha, ...allGroups.filter((id) => id !== alpha)]);
    await user.api.addTransaction({ accountId, amount: -35000, description: "COFFEE POINT" });

    await openApp(page, user);
    await gotoSection(page, "Transactions");

    const row = page.locator(".tx-grid .cat-row", { hasText: "COFFEE POINT" });
    await expect(row).toBeVisible();
    // the row's last inline select is the category picker (account comes first)
    await row.locator(".gsel").last().click();

    const groupLabels = page.locator(".gsel__drop .gsel__grp");
    await expect(groupLabels.first()).toBeVisible();
    const labels = await groupLabels.allTextContents();
    const ours = labels.filter((l) => l === "Alpha Group" || l === "Zeta Group");
    expect(ours).toEqual(["Alpha Group", "Zeta Group"]);

    // the store updates optimistically and fires the PATCH in the background —
    // wait for the server to actually accept it before reloading, or the
    // reload can win the race and the category silently reverts
    const saved = page.waitForResponse(
        (r) => r.request().method() === "PATCH" && r.url().includes("/api/transactions/") && r.ok(),
    );
    await page.locator(".gsel__drop").getByRole("option", { name: "Coffee" }).click();
    await expect(row.locator(".gsel").last()).toContainText("Coffee");
    await saved;

    await page.reload();
    await expect(page.locator(".sidebar")).toBeVisible();
    await gotoSection(page, "Transactions");
    await expect(
        page.locator(".tx-grid .cat-row", { hasText: "COFFEE POINT" }).locator(".gsel").last(),
    ).toContainText("Coffee");
});
