import { test, expect, openApp, gotoSection, YEAR, MONTH } from "./fixtures/fixtures.js";

test("a savings goal distributes to its deadline and remains discoverable when closed", async ({
    page,
    user,
}) => {
    const { id: groupId } = await user.api.createGroup("Dreams", "goal");
    await user.api.createCategory("BMW X5", groupId, "", {
        goalTarget: 60_000,
        goalTargetDate: `${YEAR}-08-31`,
    });
    const snapshot = await user.api.snapshot();
    const goal = snapshot.categories.find((category) => category.name === "BMW X5");
    await user.api.setBudget(goal.id, YEAR, MONTH, 10_000);

    await openApp(page, user);
    await gotoSection(page, "Budget");
    await page.getByText("Month", { exact: true }).click();

    const monthRow = page.locator(".cat-row", { hasText: "BMW X5" });
    const categoryCell = monthRow.locator("td").first();
    await expect(categoryCell).toBeVisible();
    await categoryCell.hover();
    await expect(page.getByRole("tooltip")).toContainText("100 / 600 ₽ · 17%");

    await monthRow.getByRole("button", { name: "Actions" }).click();
    await page.getByRole("menuitem", { name: "Distribute across months" }).click();
    const dialog = page.getByRole("dialog", { name: "Distribute BMW X5" });
    await expect(dialog.getByText("Number of months", { exact: true })).toBeVisible();
    await expect(dialog.getByRole("spinbutton")).toHaveValue("3");
    await dialog.getByRole("button", { name: "Distribute" }).click();
    await expect(dialog).toHaveCount(0);

    await categoryCell.hover();
    await expect(page.getByRole("tooltip")).toContainText("200 / 600 ₽ · 33%");

    await page.getByText("Year", { exact: true }).click();
    await page.getByText("Plan", { exact: true }).click();
    const yearRow = page.locator(".yg-row", { hasText: "BMW X5" });
    await expect(yearRow.locator("td").nth(MONTH)).toHaveText("200");
    await expect(yearRow.locator("td").nth(MONTH + 1)).toHaveText("200");
    await expect(yearRow.locator("td").nth(MONTH + 2)).toHaveText("200");

    await yearRow.getByRole("button", { name: "Actions" }).click();
    await page.getByRole("menuitem", { name: "Close goal" }).click();
    await expect(yearRow).toHaveCount(0);
    await page.getByRole("button", { name: "Show 1 unused" }).click();
    await expect(yearRow).toBeVisible();
    await yearRow.getByRole("button", { name: "Actions" }).click();
    await expect(page.getByRole("menuitem", { name: "Open goal" })).toBeVisible();
});
