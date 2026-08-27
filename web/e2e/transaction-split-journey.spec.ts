import {
    test,
    expect,
    openApp,
    gotoSection,
    reloadCurrentPage,
    YEAR,
    MONTH,
} from "./fixtures/fixtures.js";
import type { Locator, Page } from "@playwright/test";

const juneBaseCell = 1 + (MONTH - 1) * 3;

const openSplitEditor = async (page: Page, description: string, action = "Split transaction") => {
    const row = page.locator(".tx-grid .cat-row", { hasText: description });
    await row.hover();
    await row.getByRole("button", { name: "Transaction actions" }).click();
    await page.getByRole("menuitem", { name: action }).click();
    return row;
};

const choosePartCategory = async (page: Page, part: Locator, category: string) => {
    await part.locator(".gsel").click();
    await page.locator(".gsel__drop").getByRole("option", { name: category }).click();
};

test("split journey keeps allocation, budgets and dashboard visualizations consistent", async ({
    page,
    user,
}) => {
    const initial = await user.api.snapshot();
    const accountId = initial.accounts[0]!.id;
    const { id: expenseGroup } = await user.api.createGroup("Receipt categories");
    const { id: groceriesId } = await user.api.createCategory("Split groceries", expenseGroup);
    const { id: householdId } = await user.api.createCategory("Split household", expenseGroup);
    await user.api.createCategory("Split transport", expenseGroup);
    const { id: incomeGroup } = await user.api.createGroup("Split income", "income");
    await user.api.createCategory("Split salary", incomeGroup);
    await user.api.createCategory("Split bonus", incomeGroup);
    await user.api.setBudget(groceriesId, YEAR, MONTH, 60000);
    await user.api.setBudget(householdId, YEAR, MONTH, 45000);

    await user.api.addTransaction({
        accountId,
        amount: -90000,
        description: "E2E MIXED RECEIPT",
    });
    await user.api.addTransaction({
        accountId,
        amount: 50000,
        description: "E2E MIXED INCOME",
    });

    await openApp(page, user);
    await gotoSection(page, "Transactions");

    const expenseRow = await openSplitEditor(page, "E2E MIXED RECEIPT");
    const editor = page.locator(".split-editor__parts");
    let parts = editor.locator(".split-editor__part");

    // Adding and removing a part redistributes every kopeck without losing the bar.
    await page.getByRole("button", { name: "Add part" }).click();
    await expect(parts).toHaveCount(3);
    await expect(page.getByRole("slider")).toHaveCount(2);
    await expect(parts.nth(0).getByLabel("Part 1 amount")).toHaveValue("300");
    await parts.nth(2).getByRole("button", { name: "Remove part 3" }).click();
    await expect(parts).toHaveCount(2);
    await expect(page.getByRole("slider")).toHaveCount(1);

    await choosePartCategory(page, parts.nth(0), "Split groceries");
    await choosePartCategory(page, parts.nth(1), "Split household");
    await page.getByRole("button", { name: "Split evenly" }).click();
    await expect(parts.nth(0).getByLabel("Part 1 amount")).toHaveValue("450");

    // The dashboard palette is shared by the allocation bar and its category markers.
    const allocation = page.locator(".split-allocation");
    await expect(allocation).toBeVisible();
    await expect(parts.locator(".split-editor__swatch")).toHaveCount(2);
    await expect(allocation).toHaveCSS(
        "background-image",
        /rgb\(194, 65, 12\).*rgb\(66, 105, 208\)/,
    );

    // Dragging the bar updates numeric fields; manual entry updates its neighbour and keeps it visible.
    await page.getByRole("slider", { name: "Boundary between parts 1 and 2" }).fill("60000");
    await expect(parts.nth(0).getByLabel("Part 1 amount")).toHaveValue("600");
    await expect(parts.nth(1).getByLabel("Part 2 amount")).toHaveValue("300");
    await parts.nth(0).getByLabel("Part 1 amount").fill("540");
    await expect(parts.nth(1).getByLabel("Part 2 amount")).toHaveValue("360");
    await expect(allocation).toBeVisible();
    await expect(page.getByText("Fully assigned")).toBeVisible();

    const expenseSaved = page.waitForResponse(
        (response) =>
            response.request().method() === "PUT" &&
            response.url().includes("/splits") &&
            response.ok(),
    );
    await page.getByRole("button", { name: "Save split" }).click();
    await expenseSaved;
    await expect(expenseRow.getByRole("button", { name: "split · 2" })).toBeVisible();

    // Income parts use the same positive sign as their parent without asking the user for signs.
    const incomeRow = await openSplitEditor(page, "E2E MIXED INCOME");
    parts = editor.locator(".split-editor__part");
    await choosePartCategory(page, parts.nth(0), "Split salary");
    await choosePartCategory(page, parts.nth(1), "Split bonus");
    await parts.nth(0).getByLabel("Part 1 amount").fill("300");
    await expect(parts.nth(1).getByLabel("Part 2 amount")).toHaveValue("200");
    await page.getByRole("button", { name: "Save split" }).click();
    await expect(incomeRow.getByRole("button", { name: "split · 2" })).toBeVisible();
    await expect(page.locator(".ui-tab")).toHaveCount(0);

    await reloadCurrentPage(page);
    await expect(page.locator(".sidebar")).toBeVisible();
    await gotoSection(page, "Transactions");
    const reloadedExpense = page.locator(".tx-grid .cat-row", { hasText: "E2E MIXED RECEIPT" });
    await reloadedExpense.getByRole("button", { name: "split · 2" }).click();
    const splitRows = page.locator(".tx-grid .tx-row_leg");
    const groceriesPart = splitRows.filter({ hasText: "Split groceries" });
    const householdPart = splitRows.filter({ hasText: "Split household" });
    await expect(groceriesPart).toContainText("Cash");
    await expect(householdPart).toContainText("Cash");
    await expect(groceriesPart.locator(".gsel")).toHaveCount(1);
    await expect(householdPart.locator(".gsel")).toHaveCount(1);

    let snapshot = await user.api.snapshot();
    const expense = snapshot.transactions.find((tx) => tx.description === "E2E MIXED RECEIPT");
    const income = snapshot.transactions.find((tx) => tx.description === "E2E MIXED INCOME");
    expect(expense!.categoryId).toBeNull();
    expect(expense!.splits!.map((part) => part.amount)).toEqual([-54000, -36000]);
    expect(income!.splits!.map((part) => part.amount)).toEqual([30000, 20000]);
    expect(
        [...(expense!.splits ?? []), ...(income!.splits ?? [])].every(
            (part) => part.accountId == null,
        ),
    ).toBe(true);

    await gotoSection(page, "Budget");
    const groceriesBudget = page.locator(".yg-row", { hasText: "Split groceries" });
    const householdBudget = page.locator(".yg-row", { hasText: "Split household" });
    await expect(groceriesBudget.locator("td").nth(juneBaseCell)).toHaveText("600");
    await expect(groceriesBudget.locator("td").nth(juneBaseCell + 1)).toHaveText("-540");
    await expect(groceriesBudget.locator("td").nth(juneBaseCell + 2)).toHaveText("60");
    await expect(householdBudget.locator("td").nth(juneBaseCell)).toHaveText("450");
    await expect(householdBudget.locator("td").nth(juneBaseCell + 1)).toHaveText("-360");
    await expect(householdBudget.locator("td").nth(juneBaseCell + 2)).toHaveText("90");

    await gotoSection(page, "Dashboard");
    await expect(
        page.locator(".kpi", { hasText: "Spent this month" }).locator(".kpi__value"),
    ).toContainText("900");
    const expenseDonut = page.locator(".chart-card", { hasText: "Spending by category" }).first();
    await expect(expenseDonut.locator(".donut-legend")).toContainText("Split groceries");
    await expect(expenseDonut.locator(".donut-legend")).toContainText("Split household");
    const incomeDonut = page.locator(".chart-card", { hasText: "Income by category" }).first();
    await expect(incomeDonut.locator(".donut-legend")).toContainText("Split salary");
    await expect(incomeDonut.locator(".donut-legend")).toContainText("Split bonus");

    // A split child may change category, but never account; budgets and charts follow immediately.
    await gotoSection(page, "Transactions");
    const expandedExpense = page.locator(".tx-grid .cat-row", { hasText: "E2E MIXED RECEIPT" });
    await expandedExpense.getByRole("button", { name: "split · 2" }).click();
    const childHousehold = page.locator(".tx-grid .tx-row_leg", { hasText: "Split household" });
    await childHousehold.locator(".gsel").click();
    await page.locator(".gsel__drop").getByRole("option", { name: "Split groceries" }).click();
    await expect(
        page.locator(".tx-grid .tx-row_leg .gsel", { hasText: "Split groceries" }),
    ).toHaveCount(2);

    await gotoSection(page, "Budget");
    await expect(groceriesBudget.locator("td").nth(juneBaseCell + 1)).toHaveText("-900");
    await expect(groceriesBudget.locator("td").nth(juneBaseCell + 2)).toHaveText("-300");
    await expect(householdBudget.locator("td").nth(juneBaseCell + 1)).toHaveText("0");
    await expect(householdBudget.locator("td").nth(juneBaseCell + 2)).toHaveText("450");

    await gotoSection(page, "Dashboard");
    await expect(expenseDonut.locator(".donut-legend")).toContainText("Split groceries");
    await expect(expenseDonut.locator(".donut-legend")).not.toContainText("Split household");

    // Removing the split restores a normal uncategorized parent and removes stale analytics.
    await gotoSection(page, "Transactions");
    await openSplitEditor(page, "E2E MIXED RECEIPT", "Edit split");
    await page.getByRole("button", { name: "Remove split" }).click();
    await expect(page.getByText("Split removed")).toBeVisible();
    await expect(expandedExpense.getByRole("button", { name: /split ·/ })).toHaveCount(0);
    await expect(expandedExpense.locator(".gsel")).toHaveCount(2);

    snapshot = await user.api.snapshot();
    expect(
        snapshot.transactions.find((tx) => tx.description === "E2E MIXED RECEIPT")!.splits,
    ).toEqual([]);
    await gotoSection(page, "Dashboard");
    await expect(
        page.locator(".kpi", { hasText: "Spent this month" }).locator(".kpi__value"),
    ).toContainText("0");
    await expect(expenseDonut.locator(".chart-card__empty")).toHaveText(
        "No categorized entries yet",
    );
});
