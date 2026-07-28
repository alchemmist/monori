import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { api } from "../api.js";
import { useStore } from "../store.js";
import MigratePanel from "./MigratePanel.jsx";

describe("MigratePanel", () => {
    beforeEach(() => {
        resetStore();
        seed({
            accounts: [
                { id: 1, name: "Card", archived: false },
                { id: 2, name: "Cash", archived: false },
            ],
        });
        vi.clearAllMocks();
    });

    it("previews a workbook, requires every marker mapping, and commits the selected policy", async () => {
        const file = new File(["book"], "budget.xlsx", {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        });
        vi.spyOn(api, "workbookPreview").mockResolvedValue({
            groups: 2,
            categories: 3,
            transactions: 4,
            budgetCells: 5,
            errors: [{ line: 3 }],
            warnings: ["Check dates"],
            accountSlots: [
                { key: "Main", marker: "Main", currency: "RUB" },
                { key: "Savings", marker: "Savings", currency: "RUB" },
            ],
            budgetConflicts: 2,
        });
        const commit = vi.spyOn(api, "workbookCommit").mockResolvedValue({
            inserted: 4,
            skipped: 1,
            groupsCreated: 2,
            categoriesCreated: 3,
            budgetsWritten: 5,
        });
        const load = vi.spyOn(useStore.getState(), "load").mockResolvedValue();
        const { container, user } = renderUI(<MigratePanel onClose={vi.fn()} />);
        fireEvent.change(container.querySelector('input[type="file"]'), {
            target: { files: [file] },
        });
        expect(await screen.findByText(/2 groups, 3 categories/)).toBeInTheDocument();
        expect(screen.getByText(/1 rows could not be parsed/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
        const selectors = container.querySelectorAll("button.gsel");
        await user.click(selectors[0]);
        await user.click(await screen.findByText("Card"));
        // one of two markers mapped is not enough — the unmapped one would commit as NaN
        expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
        await user.click(selectors[1]);
        await user.click(await screen.findByText("Cash"));
        expect(screen.getByRole("button", { name: "Import" })).toBeEnabled();
        await user.click(screen.getByLabelText("Keep mine"));
        await user.click(screen.getByRole("button", { name: "Import" }));
        await waitFor(() =>
            expect(commit).toHaveBeenCalledWith(file, { Main: 1, Savings: 2 }, "skip", true),
        );
        expect(load).toHaveBeenCalled();
        expect(await screen.findByText(/Imported 4 transactions/)).toBeInTheDocument();
    });

    it("defaults the conflicting budget cells to being overwritten", async () => {
        const file = new File(["book"], "budget.xlsx");
        vi.spyOn(api, "workbookPreview").mockResolvedValue({
            groups: 1,
            categories: 1,
            transactions: 1,
            budgetCells: 1,
            errors: [],
            warnings: [],
            accountSlots: [{ key: "Main", marker: "Main", currency: "RUB" }],
            budgetConflicts: 3,
        });
        const commit = vi.spyOn(api, "workbookCommit").mockResolvedValue({
            inserted: 1,
            skipped: 0,
            groupsCreated: 0,
            categoriesCreated: 0,
            budgetsWritten: 1,
        });
        vi.spyOn(useStore.getState(), "load").mockResolvedValue();
        const { container, user } = renderUI(<MigratePanel onClose={vi.fn()} />);
        fireEvent.change(container.querySelector('input[type="file"]'), {
            target: { files: [file] },
        });
        await screen.findByText(/3 budget cells already exist/);
        expect(screen.getByLabelText("Overwrite")).toBeChecked();
        await user.click(container.querySelector("button.gsel"));
        await user.click(await screen.findByText("Card"));
        await user.click(screen.getByRole("button", { name: "Import" }));
        await waitFor(() =>
            expect(commit).toHaveBeenCalledWith(file, { Main: 1 }, "overwrite", true),
        );
    });

    it("reports a workbook preview failure without enabling import", async () => {
        vi.spyOn(api, "workbookPreview").mockRejectedValue(new Error("not a workbook"));
        const notify = vi.spyOn(useStore.getState(), "notify");
        const { container } = renderUI(<MigratePanel onClose={vi.fn()} />);
        fireEvent.change(container.querySelector('input[type="file"]'), {
            target: { files: [new File(["x"], "bad.xlsx")] },
        });
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Could not read workbook" }),
            ),
        );
        expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
    });

    it("offers only same-currency accounts and flags currencies with none", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", archived: false, currency: "RUB" },
                { id: 2, name: "Dollars", archived: false, currency: "USD" },
            ],
        });
        vi.spyOn(api, "workbookPreview").mockResolvedValue({
            groups: 0,
            categories: 0,
            transactions: 7,
            budgetCells: 0,
            errors: [],
            warnings: [],
            accountSlots: [
                { key: "usd", marker: "Main", currency: "USD", transactions: 5 },
                { key: "eur", marker: "Euro", currency: "EUR", transactions: 2 },
            ],
            budgetConflicts: 0,
        });
        const { container, user } = renderUI(<MigratePanel onClose={vi.fn()} />);
        fireEvent.change(container.querySelector('input[type="file"]'), {
            target: { files: [new File(["x"], "book.xlsx")] },
        });
        // a non-RUB slot spells out its currency and row count
        expect(await screen.findByText(/Account for Main · USD \(5 rows\)/)).toBeInTheDocument();
        // no EUR account exists, so those rows are called out as un-importable
        expect(screen.getByText(/Create an account held in EUR/)).toBeInTheDocument();
        // the markers carry no card digits, so the remember checkbox stays hidden
        expect(screen.queryByText(/Remember which card/)).not.toBeInTheDocument();
        // the USD slot must not offer the ruble account
        await user.click(container.querySelectorAll("button.gsel")[0]);
        expect(await screen.findByText("Dollars")).toBeInTheDocument();
        expect(screen.queryByText("Card")).not.toBeInTheDocument();
    });

    it("pre-selects the settings default account for the unmarked slot", async () => {
        seed({ accounts: [{ id: 1, name: "Card", archived: false, currency: "RUB" }] });
        useStore.setState({ user: { defaultAccountId: 1 } });
        vi.spyOn(api, "workbookPreview").mockResolvedValue({
            groups: 0,
            categories: 0,
            transactions: 3,
            budgetCells: 0,
            errors: [],
            warnings: [],
            accountSlots: [{ key: "unmarked", marker: null, currency: "RUB", transactions: 3 }],
            budgetConflicts: 0,
        });
        const commit = vi.spyOn(api, "workbookCommit").mockResolvedValue({
            inserted: 3,
            skipped: 0,
            groupsCreated: 0,
            categoriesCreated: 0,
            budgetsWritten: 0,
        });
        vi.spyOn(useStore.getState(), "load").mockResolvedValue();
        const { container, user } = renderUI(<MigratePanel onClose={vi.fn()} />);
        fireEvent.change(container.querySelector('input[type="file"]'), {
            target: { files: [new File(["x"], "book.xlsx")] },
        });
        // the unmarked slot is mapped to the default account without any pick,
        // so import is enabled straight away
        await waitFor(() =>
            expect(screen.getByRole("button", { name: "Import" })).toBeEnabled(),
        );
        await user.click(screen.getByRole("button", { name: "Import" }));
        await waitFor(() =>
            expect(commit).toHaveBeenCalledWith(
                expect.anything(),
                { unmarked: 1 },
                "overwrite",
                true,
            ),
        );
    });

    it("only offers to remember cards when a marker carries card digits", async () => {
        seed({ accounts: [{ id: 1, name: "Card", archived: false, currency: "RUB" }] });
        vi.spyOn(api, "workbookPreview").mockResolvedValue({
            groups: 0,
            categories: 0,
            transactions: 1,
            budgetCells: 0,
            errors: [],
            warnings: [],
            accountSlots: [{ key: "card", marker: "•• 1234", currency: "RUB", transactions: 1 }],
            budgetConflicts: 0,
        });
        const { container } = renderUI(<MigratePanel onClose={vi.fn()} />);
        fireEvent.change(container.querySelector('input[type="file"]'), {
            target: { files: [new File(["x"], "book.xlsx")] },
        });
        expect(await screen.findByText(/Remember which card/)).toBeInTheDocument();
    });

    it("imports a workbook without account markers and closes from its completed state", async () => {
        const file = new File(["book"], "budget.xlsx");
        vi.spyOn(api, "workbookPreview").mockResolvedValue({
            groups: 0,
            categories: 0,
            transactions: 2,
            budgetCells: 0,
            errors: [],
            warnings: [],
            accountSlots: [],
            budgetConflicts: 0,
        });
        const commit = vi.spyOn(api, "workbookCommit").mockResolvedValue({
            inserted: 2,
            skipped: 0,
            groupsCreated: 0,
            categoriesCreated: 0,
            budgetsWritten: 0,
        });
        vi.spyOn(useStore.getState(), "load").mockResolvedValue();
        const close = vi.fn();
        const { container, user } = renderUI(<MigratePanel onClose={close} />);

        fireEvent.change(container.querySelector('input[type="file"]'), {
            target: { files: [file] },
        });
        await screen.findByText(/0 groups, 0 categories, 2 transactions/);
        expect(screen.getByRole("button", { name: "Import" })).toBeEnabled();
        await user.click(screen.getByRole("button", { name: "Import" }));
        await waitFor(() => expect(commit).toHaveBeenCalledWith(file, {}, "overwrite", true));
        expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Done" }));
        expect(close).toHaveBeenCalledOnce();
    });
});
