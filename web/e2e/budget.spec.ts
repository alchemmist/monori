import {
    test,
    expect,
    openApp,
    gotoSection,
    reloadCurrentPage,
    YEAR,
    MONTH,
} from "./fixtures/fixtures.js";
import type { Locator } from "@playwright/test";

// June's "Bud" cell in the year grid: td 0 is the category name, then one td
// per month in "Plan" density.
const juneCell = (row: Locator) => row.locator("td").nth(MONTH);

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
    // a never-touched category is hidden from every budget view until asked for
    await page.getByText(/Show \d+ unused/).click();

    const row = page.locator(".yg-row", { hasText: "Groceries" });
    const june = page.locator(".yg-msum").nth(MONTH - 1);
    await expect(row).toBeVisible();
    await expect(june.locator(".yg-msum__av")).toHaveText("0 ₽");

    const displayCell = juneCell(row).locator(".budget-cell");
    await displayCell.scrollIntoViewIfNeeded();
    await expect(displayCell).toBeVisible();
    const displayBox = await displayCell.boundingBox();
    expect(displayBox).not.toBeNull();
    await displayCell.click();
    const input = juneCell(row).locator(".budget-cell__input");
    await expect(input).toBeVisible();
    const inputBox = await input.boundingBox();
    expect(inputBox).not.toBeNull();
    expect(inputBox).toEqual(displayBox);
    await input.fill("1234567");
    const filledInputBox = await input.boundingBox();
    expect(filledInputBox).not.toBeNull();
    expect(filledInputBox).toEqual(displayBox);
    await page.keyboard.press("Enter");

    await expect(displayCell).toHaveText(/1.234.567/);
    const committedBox = await displayCell.boundingBox();
    expect(committedBox).not.toBeNull();
    expect(committedBox).toEqual(displayBox);

    // nothing funds the budget, so the seven-digit budget drives June negative
    // and the whole header band recomputes in the same frame
    await expect(june.locator(".yg-msum__av")).toHaveText(/-1.234.567 ₽/);

    await reloadCurrentPage(page);
    await expect(page.locator(".sidebar")).toBeVisible();
    await page.getByText("Plan", { exact: true }).click();
    await expect(juneCell(page.locator(".yg-row", { hasText: "Groceries" }))).toHaveText(
        /1.234.567/,
    );
    await expect(
        page
            .locator(".yg-msum")
            .nth(MONTH - 1)
            .locator(".yg-msum__av"),
    ).toHaveText(/-1.234.567 ₽/);
});

test("activity and balance reflect seeded transactions", async ({ page, user }) => {
    const snap = await user.api.snapshot();
    const accountId = snap.accounts[0]!.id;
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

test("editing an account opening balance updates budget availability and restores it", async ({
    page,
    user,
}) => {
    const snap = await user.api.snapshot();
    const { id: groupId } = await user.api.createGroup("Essentials");
    const { id: categoryId } = await user.api.createCategory("Rent", groupId);
    await user.api.setBudget(categoryId, YEAR, MONTH, 10_000);

    await openApp(page, user);
    await page.getByText("Month", { exact: true }).click();
    const available = page.locator(".hero-card", { hasText: "Available to budget" });
    await expect(available.locator(".hero-card__value")).toHaveText("-100 ₽");

    await gotoSection(page, "Accounts");
    const account = page.locator(".account-row", { hasText: "Cash" });
    await account.getByRole("button", { name: "Actions" }).click();
    await page.getByRole("menuitem", { name: "Edit" }).click();

    const tab = page.locator(".ui-tab", { hasText: "Edit Cash" });
    await tab.getByLabel("Opening balance").fill("500");
    const saved = page.waitForResponse(
        (response) =>
            response.request().method() === "PATCH" &&
            response.url().includes(`/api/accounts/${snap.accounts[0]!.id}`) &&
            response.ok(),
    );
    await tab.getByRole("button", { name: "Save" }).click();
    await saved;
    await expect(tab).toHaveCount(0);

    await gotoSection(page, "Budget");
    await page.getByText("Month", { exact: true }).click();
    await expect(available.locator(".hero-card__value")).toHaveText("400 ₽");
    // The year view is a separate rendering of the same availability chain.
    await page.getByText("Year", { exact: true }).click();
    await expect(
        page
            .locator(".yg-msum")
            .nth(MONTH - 1)
            .locator(".yg-msum__av"),
    ).toHaveText("400 ₽");

    await gotoSection(page, "Accounts");
    await account.getByRole("button", { name: "Actions" }).click();
    await page.getByRole("menuitem", { name: "Edit" }).click();
    const reopenedTab = page.locator(".ui-tab", { hasText: "Edit Cash" });
    await reopenedTab.getByLabel("Opening balance").fill("0");
    const restored = page.waitForResponse(
        (response) =>
            response.request().method() === "PATCH" &&
            response.url().includes(`/api/accounts/${snap.accounts[0]!.id}`) &&
            response.ok(),
    );
    await reopenedTab.getByRole("button", { name: "Save" }).click();
    await restored;

    await gotoSection(page, "Budget");
    await page.getByText("Month", { exact: true }).click();
    await expect(available.locator(".hero-card__value")).toHaveText("-100 ₽");
});
