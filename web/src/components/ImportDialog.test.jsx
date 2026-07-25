import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api.js";
import { renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import ImportDialog from "./ImportDialog.jsx";

describe("ImportDialog", () => {
    beforeEach(() => {
        resetStore();
        vi.clearAllMocks();
        globalThis.localStorage?.clear?.();
        window.visualViewport ??= { addEventListener: () => {}, removeEventListener: () => {} };
        document.fonts ??= { addEventListener: () => {}, removeEventListener: () => {} };
    });

    it("routes a statement to its uniquely matching card and imports only fresh rows", async () => {
        seed({
            accounts: [
                { id: 1, name: "Cash", archived: false, cardTails: [] },
                { id: 2, name: "Bank card", archived: false, cardTails: ["2947"] },
            ],
        });
        vi.spyOn(api, "importPreview")
            .mockResolvedValueOnce({ rows: [{ date: "2026-07-03", card: "*2947", description: "Coffee", amount: -45000, categoryId: 2, duplicate: false }], errors: [] })
            .mockResolvedValueOnce({ rows: [{ date: "2026-07-03", card: "*2947", description: "Coffee", amount: -45000, categoryId: 2, duplicate: false }, { date: "2026-07-02", card: "*2947", description: "Old", amount: -100, duplicate: true }], errors: [] });
        const commit = vi.spyOn(useStore.getState(), "commitImport").mockResolvedValue({ inserted: 1 });
        const close = vi.fn();
        const { user } = renderUI(<ImportDialog onClose={close} />);

        await user.type(screen.getByPlaceholderText(/03\.07\.2026/), "statement");
        await user.click(screen.getByRole("button", { name: "Preview" }));
        await waitFor(() => expect(api.importPreview).toHaveBeenLastCalledWith("statement", 2));
        expect(screen.getByText("1 new")).toBeInTheDocument();
        expect(screen.getByText("1 duplicates skipped")).toBeInTheDocument();
        expect(screen.getByText("Bank card")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Import 1" }));
        await waitFor(() => expect(commit).toHaveBeenCalledWith([expect.objectContaining({ description: "Coffee" })], 2));
        await waitFor(() => expect(close).toHaveBeenCalled());
    });

    it("offers to remember an unowned card tail and saves it after importing", async () => {
        seed({ accounts: [{ id: 1, name: "Card", archived: false, cardTails: [] }] });
        vi.spyOn(api, "importPreview").mockResolvedValue({ rows: [{ date: "2026-07-03", card: "*8181", description: "Shop", amount: -1, duplicate: false }], errors: [] });
        vi.spyOn(useStore.getState(), "commitImport").mockResolvedValue({ inserted: 1 });
        const patch = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        const { user } = renderUI(<ImportDialog onClose={vi.fn()} />);
        await user.type(screen.getByPlaceholderText(/03\.07\.2026/), "statement");
        await user.click(screen.getByRole("button", { name: "Preview" }));
        expect(await screen.findByLabelText("Remember card *8181 for Card")).toBeChecked();
        await user.click(screen.getByRole("button", { name: "Import 1" }));
        await waitFor(() => expect(patch).toHaveBeenCalledWith(1, { cardTails: ["8181"] }));
    });
});
