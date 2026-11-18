import { test, expect, openApp, gotoSection } from "./fixtures/fixtures.js";
import { demoSnapshot } from "../src/demo/demoData.js";

// The "Add demo data" button replays the bundled demo dataset into the signed-in
// account through the regular API (web/src/demo/seedDemo.js). Because it rides on
// the real endpoints, it silently rots whenever an API contract shifts under it —
// a past bug dropped every transaction and transfer while still creating accounts,
// categories and budgets. This test drives the actual button and checks the whole
// dataset lands, so any future drift shows up as a red test instead of an empty
// ledger nobody notices.
test("Add demo data seeds the whole demo dataset through the API", async ({ page, user }) => {
    const before = await user.api.snapshot();
    expect(before.transactions.length, "user starts empty").toBe(0);

    await openApp(page, user);
    await gotoSection(page, "Settings");
    await page.getByRole("button", { name: "Add demo data" }).click();

    // Success — not the "Could not add demo data" failure toast the bug produced.
    await expect(page.getByText("Demo data added")).toBeVisible();
    await expect(page.getByText("Could not add demo data")).toHaveCount(0);

    const after = await user.api.snapshot();
    const expectedTransferLegs = demoSnapshot.transactions.filter(
        (t) => t.transferId != null && t.transferId !== "",
    ).length;
    const seededTransferLegs = after.transactions.filter((t) => t.transferId != null).length;

    // Measured as deltas over the empty starting point (registration ships a
    // single default Cash account) and keyed to demoSnapshot itself, so growing
    // the demo keeps the test honest: whatever the dataset holds must seed.
    expect(after.accounts.length - before.accounts.length).toBe(demoSnapshot.accounts.length);
    expect(after.categories.length - before.categories.length).toBe(demoSnapshot.categories.length);
    expect(after.budgets.length - before.budgets.length).toBe(demoSnapshot.budgets.length);
    expect(after.transactions.length - before.transactions.length).toBe(
        demoSnapshot.transactions.length,
    );
    expect(seededTransferLegs, "transfer legs must be created").toBe(expectedTransferLegs);
});
