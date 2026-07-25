import { test, expect, openApp, gotoSection } from "./fixtures/fixtures.js";

// The kanban drag is custom pointer-event DnD with a 5px start threshold, so
// the mouse has to travel in real steps for the board to pick the drag up.
async function dragColumn(page, fromGid, toGid) {
    const from = page.locator(`.kb-col[data-gid="${fromGid}"] .kb-col__head`);
    const to = page.locator(`.kb-col[data-gid="${toGid}"] .kb-col__head`);
    const a = await from.boundingBox();
    const b = await to.boundingBox();
    const startX = a.x + a.width / 2;
    const startY = a.y + a.height / 2;
    const endX = b.x + 8;
    const endY = b.y + b.height / 2;
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    for (let i = 1; i <= 12; i++) {
        await page.mouse.move(
            startX + ((endX - startX) * i) / 12,
            startY + ((endY - startY) * i) / 12,
        );
    }
    await page.mouse.up();
}

test("reordering a group on the kanban carries into the budget grid", async ({ page, user }) => {
    const { id: first } = await user.api.createGroup("First Group");
    const { id: second } = await user.api.createGroup("Second Group");
    await user.api.createCategory("Alpha Cat", first);
    await user.api.createCategory("Beta Cat", second);

    await openApp(page, user);
    await gotoSection(page, "Categories");
    await expect(page.locator(`.kb-col[data-gid="${first}"]`)).toBeVisible();

    await dragColumn(page, second, first);

    const order = async () =>
        (
            await page
                .locator(".kb-col[data-gid]")
                .evaluateAll((els) => els.map((e) => e.dataset.gid))
        )
            .map(Number)
            .filter((id) => id === first || id === second);
    await expect.poll(order).toEqual([second, first]);

    // the new order survives a reload (persisted through the reorder API) ...
    await page.reload();
    await expect(page.locator(".sidebar")).toBeVisible();
    await gotoSection(page, "Categories");
    await expect.poll(order).toEqual([second, first]);

    // ... and the budget grid lists the groups in the same kanban order
    await gotoSection(page, "Budget");
    const rows = page.locator(".yg-group", { hasText: /First Group|Second Group/ });
    await expect(rows.first()).toContainText("Second Group");
    await expect(rows.nth(1)).toContainText("First Group");
});
