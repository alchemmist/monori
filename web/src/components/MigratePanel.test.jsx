import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { api } from "../api.js";
import { useStore } from "../store.js";
import MigratePanel from "./MigratePanel.jsx";

describe("MigratePanel", () => {
    beforeEach(() => { resetStore(); seed({ accounts: [{ id: 1, name: "Card", archived: false }, { id: 2, name: "Cash", archived: false }] }); vi.clearAllMocks(); });

    it("previews a workbook, requires every marker mapping, and commits the selected policy", async () => {
        const file = new File(["book"], "budget.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
        vi.spyOn(api, "workbookPreview").mockResolvedValue({ groups: 2, categories: 3, transactions: 4, budgetCells: 5, errors: [{ line: 3 }], warnings: ["Check dates"], accountMarkers: ["Main", "Savings"], budgetConflicts: 2 });
        const commit = vi.spyOn(api, "workbookCommit").mockResolvedValue({ inserted: 4, skipped: 1, groupsCreated: 2, categoriesCreated: 3, budgetsWritten: 5 });
        const load = vi.spyOn(useStore.getState(), "load").mockResolvedValue();
        const { container, user } = renderUI(<MigratePanel onClose={vi.fn()} />);
        fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [file] } });
        expect(await screen.findByText(/2 groups, 3 categories/)).toBeInTheDocument();
        expect(screen.getByText(/1 rows could not be parsed/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
        const selectors = container.querySelectorAll("button.gsel");
        await user.click(selectors[0]); await user.click(await screen.findByText("Card"));
        await user.click(selectors[1]); await user.click(await screen.findByText("Cash"));
        await user.click(screen.getByLabelText("Keep mine"));
        await user.click(screen.getByRole("button", { name: "Import" }));
        await waitFor(() => expect(commit).toHaveBeenCalledWith(file, { Main: 1, Savings: 2 }, "skip"));
        expect(load).toHaveBeenCalled();
        expect(await screen.findByText(/Imported 4 transactions/)).toBeInTheDocument();
    });

    it("reports a workbook preview failure without enabling import", async () => {
        vi.spyOn(api, "workbookPreview").mockRejectedValue(new Error("not a workbook"));
        const notify = vi.spyOn(useStore.getState(), "notify");
        const { container } = renderUI(<MigratePanel onClose={vi.fn()} />);
        fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(["x"], "bad.xlsx")] } });
        await waitFor(() => expect(notify).toHaveBeenCalledWith(expect.objectContaining({ title: "Could not read workbook" })));
        expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
    });
});
