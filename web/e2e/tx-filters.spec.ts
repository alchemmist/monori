import { test, expect, openApp, gotoSection, YEAR } from "./fixtures/fixtures.js";
import type { Page } from "@playwright/test";
import type { TestUser } from "./fixtures/fixtures.js";

// One seeded ledger, exercised by every filter on the transactions toolbar:
// search, category, year, account, hidden, amount — alone and stacked. The
// rows are chosen so each filter has something only it can isolate.
const seed = async (user: TestUser) => {
    const snap = await user.api.snapshot();
    const cash = snap.accounts[0]!.id;
    const { id: card } = await user.api.createAccount({ name: "Travel Card", type: "card" });
    const { id: daily } = await user.api.createGroup("Daily");
    const { id: coffee } = await user.api.createCategory("Coffee", daily);
    const { id: rent } = await user.api.createCategory("Rent", daily);

    const rows: [string, number, number, number | null, string, string][] = [
        // description, amount (kopecks), account, category, date, comment
        ["COFFEE POINT", -35000, cash, coffee, `${YEAR}-06-10T12:00:00`, ""],
        ["RENT JUNE", -9000000, cash, rent, `${YEAR}-06-01T12:00:00`, "flat"],
        ["AIRLINE TICKET", -4500000, card, null, `${YEAR}-06-05T12:00:00`, "trip to Kazan"],
        ["SALARY", 15000000, cash, null, `${YEAR}-06-03T12:00:00`, ""],
        ["OLD PURCHASE", -120000, cash, null, `${YEAR - 1}-11-20T12:00:00`, ""],
    ];
    for (const [description, amount, accountId, categoryId, date, comment] of rows) {
        await user.api.addTransaction({
            description,
            amount,
            accountId,
            categoryId,
            date,
            comment,
        });
    }
    return { cash, card, coffee, rent };
};

const row = (page: Page, text: string) => page.locator(".tx-grid .cat-row", { hasText: text });
const rowCount = (page: Page) => page.locator(".tx-grid .cat-row");

// the toolbar selects are InlineSelect buttons (.gsel) with a shared dropdown
const pickFilter = async (page: Page, current: string, option: string) => {
    await page.locator(".budget-toolbar .gsel", { hasText: current }).click();
    await page.locator(".gsel__drop").getByRole("option", { name: option, exact: true }).click();
};

test("search, category, year and account each narrow the ledger on their own", async ({
    page,
    user,
}) => {
    await seed(user);
    await openApp(page, user);
    await gotoSection(page, "Transactions");
    await expect(rowCount(page)).toHaveCount(5);

    // search matches the description...
    const search = page.getByLabel("Search description or comment");
    await search.fill("coffee");
    await expect(rowCount(page)).toHaveCount(1);
    await expect(row(page, "COFFEE POINT")).toBeVisible();
    // ...and the comment, which is not the description
    await search.fill("kazan");
    await expect(rowCount(page)).toHaveCount(1);
    await expect(row(page, "AIRLINE TICKET")).toBeVisible();
    await search.fill("");
    await expect(rowCount(page)).toHaveCount(5);

    // one category
    await pickFilter(page, "All categories", "Coffee");
    await expect(rowCount(page)).toHaveCount(1);
    await expect(row(page, "COFFEE POINT")).toBeVisible();

    // everything without one
    await pickFilter(page, "Coffee", "Uncategorized");
    await expect(rowCount(page)).toHaveCount(3);
    await expect(row(page, "RENT JUNE")).toHaveCount(0);
    await pickFilter(page, "Uncategorized", "All categories");

    // a year the ledger only has one row in
    await pickFilter(page, "All years", String(YEAR - 1));
    await expect(rowCount(page)).toHaveCount(1);
    await expect(row(page, "OLD PURCHASE")).toBeVisible();
    await pickFilter(page, String(YEAR - 1), "All years");

    // the second account, which owns exactly one row
    await pickFilter(page, "All accounts", "Travel Card");
    await expect(rowCount(page)).toHaveCount(1);
    await expect(row(page, "AIRLINE TICKET")).toBeVisible();
    await pickFilter(page, "Travel Card", "All accounts");
    await expect(rowCount(page)).toHaveCount(5);
});

test("the amount range covers both signs and rescales as other filters narrow", async ({
    page,
    user,
}) => {
    await seed(user);
    await openApp(page, user);
    await gotoSection(page, "Transactions");

    // the scale spans the largest expense to the largest income
    await page.locator(".tx-amount-filter__button").click();
    const panel = page.locator(".tx-amount-filter");
    const scale = panel.locator(".tx-amount-filter__scale");
    await expect(scale).toContainText("-90 000");
    await expect(scale).toContainText("150 000");

    // pulling the lower handle up drops the two biggest expenses
    const lower = panel.getByRole("slider").first();
    const box = await lower.boundingBox();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box!.x + box!.width / 2 + 90, box!.y + box!.height / 2, { steps: 10 });
    await page.mouse.up();
    await expect(row(page, "RENT JUNE")).toHaveCount(0);
    await expect(row(page, "AIRLINE TICKET")).toHaveCount(0);
    await expect(row(page, "SALARY")).toBeVisible();
    // the button carries the active range and the panel counts what survived
    await expect(page.locator(".tx-amount-filter__button")).not.toContainText("Amount");
    await expect(panel.locator(".tx-amount-filter__foot")).toContainText("of 5 shown");

    await panel.getByRole("button", { name: "Reset" }).click();
    await expect(rowCount(page)).toHaveCount(5);

    // narrowing another filter rescales the slider to what is left
    await page.keyboard.press("Escape");
    await pickFilter(page, "All categories", "Uncategorized");
    await page.locator(".tx-amount-filter__button").click();
    await expect(scale).toContainText("-45 000");
    await expect(scale).not.toContainText("-90 000");

    // and with a single row left there is no range to pick: the control goes
    await page.keyboard.press("Escape");
    await pickFilter(page, "All accounts", "Travel Card");
    await expect(page.locator(".tx-amount-filter__button")).toHaveCount(0);
});

test("filters stack, and hidden rows join the ledger only when asked", async ({ page, user }) => {
    await seed(user);
    await openApp(page, user);
    await gotoSection(page, "Transactions");

    // hide the income, it leaves every view
    const salary = row(page, "SALARY");
    await salary.hover();
    const hidden = page.waitForResponse(
        (r) => r.request().method() === "PATCH" && r.url().includes("/api/transactions/") && r.ok(),
    );
    await salary.getByRole("button", { name: "Hide transaction" }).click();
    await hidden;
    await expect(rowCount(page)).toHaveCount(4);

    // the toggle brings it back, highlighted, and the amount scale grows with it
    await page.getByRole("button", { name: "Hidden" }).click();
    await expect(page.locator(".tx-grid .tx-hidden-row", { hasText: "SALARY" })).toBeVisible();
    await page.locator(".tx-amount-filter__button").click();
    await expect(page.locator(".tx-amount-filter__scale")).toContainText("150 000");
    await page.keyboard.press("Escape");

    // search + category + account stack instead of replacing each other
    await page.getByRole("button", { name: "Hidden" }).click();
    await pickFilter(page, "All categories", "Uncategorized");
    await expect(rowCount(page)).toHaveCount(2); // ticket + old purchase
    await pickFilter(page, "All accounts", "Travel Card");
    await expect(rowCount(page)).toHaveCount(1);
    await expect(row(page, "AIRLINE TICKET")).toBeVisible();
    await page.getByLabel("Search description or comment").fill("coffee");
    // coffee is on the other account and has a category: nothing can match
    await expect(rowCount(page)).toHaveCount(0);
    await expect(page.locator(".tx-grid")).toContainText("Nothing found");
});
