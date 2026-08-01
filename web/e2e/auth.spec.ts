import { test, expect, gotoSection, openApp } from "./fixtures/fixtures.js";

// The one spec that drives the real auth UI; every other spec logs in
// programmatically via the token (see openApp) and stays focused on its
// feature.

test("registering through the login page lands in the authed app", async ({ page }) => {
    const email = `e2e-ui-register-${Date.now()}@example.com`;
    await page.goto("/login");
    await page.locator(".login__switch button", { hasText: "Register" }).click();
    await page.getByPlaceholder("Email").fill(email);
    await page.getByPlaceholder("Password (min 8 characters)").fill("e2e-password-123");
    await page.locator(".login__submit").click();
    await expect(page.locator(".sidebar")).toBeVisible();
    await expect(page.locator(".page-title").first()).toHaveText("Budget");
});

test("signing in through the login page lands in the authed app", async ({ page, user }) => {
    await page.goto("/login");
    await page.getByPlaceholder("Email").fill(user.email);
    await page.getByPlaceholder("Password", { exact: true }).fill(user.password);
    await page.locator(".login__submit").click();
    await expect(page.locator(".sidebar")).toBeVisible();
});

test("a wrong password shows an error and stays on the login page", async ({ page, user }) => {
    await page.goto("/login");
    await page.getByPlaceholder("Email").fill(user.email);
    await page.getByPlaceholder("Password", { exact: true }).fill("definitely-wrong");
    await page.locator(".login__submit").click();
    await expect(page.locator(".login__error")).toBeVisible();
    await expect(page.locator(".sidebar")).not.toBeVisible();
});

test("logging out from settings leaves the app", async ({ page, user }) => {
    await openApp(page, user);
    await gotoSection(page, "Settings");
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/welcome$/);
    await expect(page.locator(".sidebar")).not.toBeVisible();
});
