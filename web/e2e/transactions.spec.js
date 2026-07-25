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

test("hiding a transaction removes it everywhere and the toggle brings it back", async ({
    page,
    user,
}) => {
    const snap = await user.api.snapshot();
    const accountId = snap.accounts[0].id;
    await user.api.addTransaction({ accountId, amount: -1000, description: "KEEP ME" });
    await user.api.addTransaction({ accountId, amount: -66600, description: "JUNK ROW" });

    await openApp(page, user);
    await gotoSection(page, "Transactions");

    const junk = page.locator(".tx-grid .cat-row", { hasText: "JUNK ROW" });
    await expect(junk).toBeVisible();
    const hidden = page.waitForResponse(
        (r) => r.request().method() === "PATCH" && r.url().includes("/api/transactions/") && r.ok(),
    );
    await junk.hover();
    await junk.getByRole("button", { name: "Hide transaction" }).click();
    await expect(junk).toHaveCount(0);
    await hidden;

    // gone for real: a reload rebuilds from the server snapshot
    await page.reload();
    await expect(page.locator(".sidebar")).toBeVisible();
    await gotoSection(page, "Transactions");
    await expect(page.locator(".tx-grid .cat-row", { hasText: "KEEP ME" })).toBeVisible();
    await expect(page.locator(".tx-grid .cat-row", { hasText: "JUNK ROW" })).toHaveCount(0);

    // the toggle surfaces it, highlighted, with a way back
    await page.getByRole("button", { name: "Hidden" }).click();
    const back = page.locator(".tx-grid .tx-hidden-row", { hasText: "JUNK ROW" });
    await expect(back).toBeVisible();
    const unhidden = page.waitForResponse(
        (r) => r.request().method() === "PATCH" && r.url().includes("/api/transactions/") && r.ok(),
    );
    await back.getByRole("button", { name: "Unhide transaction" }).click();
    await unhidden;
    await expect(page.locator(".tx-grid .tx-hidden-row")).toHaveCount(0);
    await expect(page.locator(".tx-grid .cat-row", { hasText: "JUNK ROW" })).toBeVisible();
});

test("the add-transaction tab records rows one after another without closing", async ({
    page,
    user,
}) => {
    const { id: group } = await user.api.createGroup("Daily");
    await user.api.createCategory("Coffee", group);

    await openApp(page, user);
    await gotoSection(page, "Transactions");
    await page.getByRole("button", { name: "Add transaction" }).click();

    const tab = page.locator(".ui-tab");
    await expect(tab).toBeVisible();
    await tab.getByLabel("Amount").fill("123.45");
    await tab.getByLabel("Description").fill("MANUAL ONE");
    // the category is picked once here and then stays on for every later row
    await tab.locator(".gsel").last().click();
    await page.locator(".gsel__drop").getByRole("option", { name: "Coffee" }).click();

    const first = page.waitForResponse(
        (r) => r.request().method() === "POST" && r.url().endsWith("/api/transactions") && r.ok(),
    );
    await tab.getByRole("button", { name: "Add", exact: true }).click();
    await first;

    // the row lands in the ledger and the tab stays open, cleared for the next
    await expect(page.locator(".tx-grid .cat-row", { hasText: "MANUAL ONE" })).toBeVisible();
    await expect(tab).toBeVisible();
    await expect(tab.getByLabel("Amount")).toHaveValue("");
    await expect(tab.getByLabel("Description")).toHaveValue("");

    const second = page.waitForResponse(
        (r) => r.request().method() === "POST" && r.url().endsWith("/api/transactions") && r.ok(),
    );
    await tab.getByLabel("Amount").fill("50");
    await tab.getByLabel("Description").fill("MANUAL TWO");
    await tab.getByRole("button", { name: "Add", exact: true }).click();
    await second;

    // both rows survive a reload, on the category that stayed picked
    await page.reload();
    await expect(page.locator(".sidebar")).toBeVisible();
    await gotoSection(page, "Transactions");
    const one = page.locator(".tx-grid .cat-row", { hasText: "MANUAL ONE" });
    const two = page.locator(".tx-grid .cat-row", { hasText: "MANUAL TWO" });
    await expect(one.locator(".gsel").last()).toContainText("Coffee");
    await expect(two.locator(".gsel").last()).toContainText("Coffee");

    // and they are real manual rows on the server, in kopecks, as expenses
    const saved = (await user.api.snapshot()).transactions.filter((t) => t.source === "manual");
    expect(saved.map((t) => [t.description, t.amount])).toEqual([
        ["MANUAL ONE", -12345],
        ["MANUAL TWO", -5000],
    ]);
});
