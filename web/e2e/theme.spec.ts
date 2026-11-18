import { test, expect, openApp, gotoSection, reloadCurrentPage } from "./fixtures/fixtures.js";

test("switching to dark applies the theme and survives a reload", async ({ page, user }) => {
    await openApp(page, user);
    await expect(page.locator("body")).not.toHaveClass(/theme-dark/);

    await gotoSection(page, "Settings");
    await page.getByText("Dark", { exact: true }).click();
    await expect(page.locator("body")).toHaveClass(/theme-dark/);

    await reloadCurrentPage(page);
    await expect(page.locator(".sidebar")).toBeVisible();
    await expect(page.locator("body")).toHaveClass(/theme-dark/);
});
