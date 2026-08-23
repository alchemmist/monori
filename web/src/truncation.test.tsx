import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderUI, resetStore, screen, seed, tx } from "./test/render.jsx";

// jsdom never applies the app's stylesheets, so a class like `.kb-card__name`
// resolves to nothing under getComputedStyle. To prove the real CSS clips long
// names we read the actual .css file off disk and inject it as a <style>, which
// getComputedStyle *does* honour. That guards both ends: the element must carry
// the class in the JSX, and the class must still define the clipping in the CSS.
vi.mock("./api.js");
vi.mock("./components/ImportDialog.jsx", () => ({ default: () => null }));
vi.mock("./components/TransferDialog.jsx", () => ({ default: () => null }));

import TransactionsPage from "./pages/TransactionsPage.jsx";
import CategoriesPage from "./pages/CategoriesPage.jsx";
import YearGrid from "./components/YearGrid.jsx";
import type { ComponentProps } from "react";

const injected: HTMLStyleElement[] = [];
const injectCss = (rel: string) => {
    const style = document.createElement("style");
    style.textContent = readFileSync(resolve(process.cwd(), rel), "utf8");
    document.head.appendChild(style);
    injected.push(style);
};
afterEach(() => {
    injected.splice(0).forEach((s) => s.remove());
});

// long, and with unbreakable runs, so a missing clip would visibly overflow
const LONG_DESC =
    "Annual reimbursement for the offsite team dinner, taxis and the after-party " +
    "Supercalifragilisticexpialidocious".repeat(3);
const LONG_CAT =
    "Extraordinarily verbose discretionary spending " +
    "Pneumonoultramicroscopicsilicovolcanoconiosis".repeat(3);

describe("long names never break the layout", () => {
    it("clips a very long transaction description and comment in the ledger", () => {
        resetStore();
        injectCss("src/pages/budget.css");
        seed({ transactions: [tx(1, { description: LONG_DESC, comment: LONG_CAT })] });
        const { container } = renderUI(<TransactionsPage />);

        // the table itself cannot widen past the viewport: fixed layout pins the
        // columns to the header, and it is deliberately not a scroll container
        const table = container.querySelector<HTMLElement>(".tx-grid")!;
        const tcs = getComputedStyle(table);
        expect(tcs.tableLayout).toBe("fixed");
        expect(tcs.overflow).toBe("visible");

        // the description cell holds the whole string but clips it with an
        // ellipsis inside a bounded width
        const descCell = screen.getByLabelText("Description").closest<HTMLElement>("td")!;
        expect(descCell).toHaveTextContent(LONG_DESC);
        const dcs = getComputedStyle(descCell);
        expect(dcs.overflow).toBe("hidden");
        expect(dcs.textOverflow).toBe("ellipsis");
        expect(dcs.maxWidth).toBe("380px");

        // the comment column has no width of its own; the shared .tx-grid td rule
        // is what keeps a long comment from spilling
        const commentCell = screen.getByLabelText("Comment").closest<HTMLElement>("td")!;
        const ccs = getComputedStyle(commentCell);
        expect(ccs.overflow).toBe("hidden");
        expect(ccs.textOverflow).toBe("ellipsis");
    });

    it("clips a very long category name on the board and in the budget grid", () => {
        // the categories board card
        resetStore();
        injectCss("src/pages/categories.css");
        seed({
            groups: [{ id: 2, name: "Spending", kind: "expense", sort: 1 }],
            categories: [
                { id: 5, groupId: 2, name: LONG_CAT, keywords: "", sort: 1, archived: false },
            ],
            transactions: [],
        });
        const board = renderUI(<CategoriesPage />).container;
        const cardName = board.querySelector<HTMLElement>(".kb-card__name")!;
        expect(cardName).toHaveTextContent(LONG_CAT);
        const ncs = getComputedStyle(cardName);
        expect(ncs.overflow).toBe("hidden");
        expect(ncs.textOverflow).toBe("ellipsis");
        expect(ncs.whiteSpace).toBe("nowrap");

        // the same name down the left rail of the yearly budget grid
        injectCss("src/components/yeargrid.css");
        const emptyMonths = () =>
            Array.from({ length: 12 }, () => ({ budgeted: 0, outflows: 0, balance: 0 }));
        const props = {
            res: {
                year: 2026,
                available: Array.from({ length: 12 }, (): number => 0),
                overspent: Array.from({ length: 12 }, (): number => 0),
                income: Array.from({ length: 12 }, (): number => 0),
                budgetedTotal: Array.from({ length: 12 }, (): number => 0),
                byCategory: new Map([[5, emptyMonths()]]),
            },
            prevRes: null,
            groups: [{ id: 7, name: "Home", kind: "expense", sort: 1 }],
            catsByGroup: new Map([
                [
                    7,
                    [{ id: 5, groupId: 7, name: LONG_CAT, keywords: "", sort: 1, archived: false }],
                ],
            ]),
            year: 2026,
            currentMonth: 0,
            cols: ["budgeted", "activity", "balance"] as ComponentProps<typeof YearGrid>["cols"],
            collapsed: {},
            setCollapsed: vi.fn(),
            setBudget: vi.fn(),
            onSelectBudget: vi.fn(),
            onCategoryMenu: () => [],
            onAddCategory: vi.fn(),
        };
        const grid = renderUI(<YearGrid {...props} />).container;
        const gridLabel = grid.querySelector<HTMLElement>(".yg-cat-label")!;
        expect(gridLabel).toHaveTextContent(LONG_CAT);
        const gcs = getComputedStyle(gridLabel);
        expect(gcs.overflow).toBe("hidden");
        expect(gcs.textOverflow).toBe("ellipsis");
    });
});
