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

test("editing a row in place rewrites it on the server, and delete removes it", async ({
    page,
    user,
}) => {
    const snap = await user.api.snapshot();
    const accountId = snap.accounts[0].id;
    await user.api.addTransaction({
        accountId,
        amount: -100000,
        description: "TYPO ROW",
        date: "2026-06-10T12:00:00",
    });
    await user.api.addTransaction({ accountId, amount: -2500, description: "DOOMED ROW" });

    await openApp(page, user);
    await gotoSection(page, "Transactions");

    const row = page.locator(".tx-grid .cat-row", { hasText: "TYPO ROW" });
    await expect(row).toBeVisible();

    const patched = () =>
        page.waitForResponse(
            (r) =>
                r.request().method() === "PATCH" &&
                r.url().includes("/api/transactions/") &&
                r.ok(),
        );
    const editField = async (where, label, value) => {
        const saved = patched();
        await where.getByRole("button", { name: label }).click();
        await where.getByLabel(label).fill(value);
        await where.getByLabel(label).press("Enter");
        await saved;
    };

    // the amount and the restored comment column, in place
    await editField(row, "Amount", "-1234.50");
    await editField(row, "Comment", "was a typo");

    // the description is reached through the comment instead: an open input's
    // value is not row text, so a filter on the old description would stop
    // matching the moment the field opens
    const edited = page.locator(".tx-grid .cat-row", { hasText: "was a typo" });
    await editField(edited, "Description", "FIXED ROW");

    await expect(page.locator(".tx-grid .cat-row", { hasText: "FIXED ROW" })).toContainText(
        "was a typo",
    );

    // the comment is searchable too, alongside the description
    await page.getByLabel("Search description or comment").fill("was a typo");
    await expect(page.locator(".tx-grid .cat-row")).toHaveCount(1);
    await page.getByLabel("Search description or comment").fill("");

    // deleting asks first, then the row is gone for good
    const doomed = page.locator(".tx-grid .cat-row", { hasText: "DOOMED ROW" });
    await doomed.hover();
    await doomed.getByRole("button", { name: "Transaction actions" }).click();
    await page.getByRole("menuitem", { name: "Delete transaction" }).click();
    const removed = page.waitForResponse(
        (r) =>
            r.request().method() === "DELETE" && r.url().includes("/api/transactions/") && r.ok(),
    );
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await removed;
    await expect(doomed).toHaveCount(0);

    // and the server agrees on all of it after a reload
    const after = (await user.api.snapshot()).transactions;
    expect(after.some((t) => t.description === "DOOMED ROW")).toBe(false);
    const fixed = after.find((t) => t.description === "FIXED ROW");
    expect(fixed).toMatchObject({ amount: -123450, comment: "was a typo" });
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

test("splitting a transaction assigns every kopeck and expands into category parts", async ({
    page,
    user,
}) => {
    const snap = await user.api.snapshot();
    const { id: groupId } = await user.api.createGroup("Receipt");
    await user.api.createCategory("Groceries", groupId);
    await user.api.createCategory("Household", groupId);
    await user.api.addTransaction({
        accountId: snap.accounts[0].id,
        amount: -100000,
        description: "MIXED RECEIPT",
    });

    await openApp(page, user);
    await gotoSection(page, "Transactions");
    const row = page.locator(".tx-grid .cat-row", { hasText: "MIXED RECEIPT" });
    await row.hover();
    await row.getByRole("button", { name: "Transaction actions" }).click();
    await page.getByRole("menuitem", { name: "Split transaction" }).click();

    const editor = page.locator(".split-editor__parts");
    const parts = editor.locator(".split-editor__part");
    await parts.nth(0).locator(".gsel").click();
    await page.locator(".gsel__drop").getByRole("option", { name: "Groceries" }).click();
    await parts.nth(0).getByLabel("Part 1 amount").fill("600");
    await parts.nth(1).locator(".gsel").click();
    await page.locator(".gsel__drop").getByRole("option", { name: "Household" }).click();
    await expect(parts.nth(1).getByLabel("Part 2 amount")).toHaveValue("400");
    await expect(page.getByText("Fully assigned")).toBeVisible();

    const saved = page.waitForResponse(
        (response) =>
            response.request().method() === "PUT" &&
            response.url().includes("/splits") &&
            response.ok(),
    );
    await page.getByRole("button", { name: "Save split" }).click();
    await saved;

    await expect(row.getByRole("button", { name: "split · 2" })).toBeVisible();
    await row.getByRole("button", { name: "split · 2" }).click();
    await expect(page.locator(".tx-grid .tx-row_leg", { hasText: "Groceries" })).toBeVisible();
    await expect(page.locator(".tx-grid .tx-row_leg", { hasText: "Household" })).toBeVisible();

    const transaction = (await user.api.snapshot()).transactions.find(
        (candidate) => candidate.description === "MIXED RECEIPT",
    );
    expect(transaction.categoryId).toBeNull();
    expect(transaction.splits.map((part) => part.amount)).toEqual([-60000, -40000]);
});
