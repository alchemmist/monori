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
            .mockResolvedValueOnce({
                rows: [
                    {
                        date: "2026-07-03",
                        card: "*2947",
                        description: "Coffee",
                        amount: -45000,
                        categoryId: 2,
                        duplicate: false,
                    },
                ],
                errors: [],
            })
            .mockResolvedValueOnce({
                rows: [
                    {
                        date: "2026-07-03",
                        card: "*2947",
                        description: "Coffee",
                        amount: -45000,
                        categoryId: 2,
                        duplicate: false,
                    },
                    {
                        date: "2026-07-02",
                        card: "*2947",
                        description: "Old",
                        amount: -100,
                        duplicate: true,
                    },
                ],
                errors: [],
            });
        const commit = vi
            .spyOn(useStore.getState(), "commitImport")
            .mockResolvedValue({ inserted: 1 });
        const close = vi.fn();
        const { user } = renderUI(<ImportDialog onClose={close} />);

        await user.type(screen.getByPlaceholderText(/03\.07\.2026/), "statement");
        await user.click(screen.getByRole("button", { name: "Preview" }));
        await waitFor(() => expect(api.importPreview).toHaveBeenLastCalledWith("statement", 2));
        expect(screen.getByText("1 new")).toBeInTheDocument();
        expect(screen.getByText("1 duplicates skipped")).toBeInTheDocument();
        expect(screen.getByText("Bank card")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Import 1" }));
        await waitFor(() =>
            expect(commit).toHaveBeenCalledWith(
                [expect.objectContaining({ description: "Coffee" })],
                2,
            ),
        );
        await waitFor(() => expect(close).toHaveBeenCalled());
    });

    it("offers to remember an unowned card tail and saves it after importing", async () => {
        seed({ accounts: [{ id: 1, name: "Card", archived: false, cardTails: [] }] });
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "*8181",
                    description: "Shop",
                    amount: -1,
                    duplicate: false,
                },
            ],
            errors: [],
        });
        vi.spyOn(useStore.getState(), "commitImport").mockResolvedValue({ inserted: 1 });
        const patch = vi.spyOn(useStore.getState(), "patchAccount").mockResolvedValue();
        const { user } = renderUI(<ImportDialog onClose={vi.fn()} />);
        await user.type(screen.getByPlaceholderText(/03\.07\.2026/), "statement");
        await user.click(screen.getByRole("button", { name: "Preview" }));
        expect(await screen.findByLabelText("Remember card *8181 for Card")).toBeChecked();
        await user.click(screen.getByRole("button", { name: "Import 1" }));
        await waitFor(() => expect(patch).toHaveBeenCalledWith(1, { cardTails: ["8181"] }));
    });

    it("does not offer to remember a tail that already belongs to an account", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", archived: false, cardTails: [] },
                { id: 2, name: "Other card", archived: false, cardTails: ["8181"] },
            ],
        });
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "*8181",
                    description: "Shop",
                    amount: -1,
                    duplicate: false,
                },
            ],
            errors: [],
        });
        const { user } = renderUI(<ImportDialog onClose={vi.fn()} />);
        await user.type(screen.getByPlaceholderText(/03\.07\.2026/), "statement");
        await user.click(screen.getByRole("button", { name: "Preview" }));
        await screen.findByText("1 new");
        expect(screen.queryByLabelText(/Remember card \*8181/)).not.toBeInTheDocument();
    });

    it("shows parsing errors, allows going back, and does not remember an unchecked tail", async () => {
        seed({ accounts: [{ id: 1, name: "Card", archived: false, cardTails: [] }] });
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "*8181",
                    description: "Shop",
                    amount: -1,
                    duplicate: false,
                },
            ],
            errors: [{ line: 4, error: "bad date" }],
        });
        const commit = vi
            .spyOn(useStore.getState(), "commitImport")
            .mockResolvedValue({ inserted: 1 });
        const patch = vi.spyOn(useStore.getState(), "patchAccount");
        const { user } = renderUI(<ImportDialog onClose={vi.fn()} />);
        await user.type(screen.getByPlaceholderText(/03\.07\.2026/), "statement");
        await user.click(screen.getByRole("button", { name: "Preview" }));
        expect(await screen.findByText("1 unparsed lines")).toBeInTheDocument();
        expect(screen.getByText("line 4: bad date")).toBeInTheDocument();
        await user.click(screen.getByLabelText("Remember card *8181 for Card"));
        await user.click(screen.getByRole("button", { name: "Import 1" }));
        await waitFor(() => expect(commit).toHaveBeenCalled());
        expect(patch).not.toHaveBeenCalled();
    });

    it("reports preview and import errors and clears a preview when account changes", async () => {
        seed({
            accounts: [
                { id: 1, name: "Card", archived: false },
                { id: 2, name: "Cash", archived: false },
            ],
        });
        const notify = vi.spyOn(useStore.getState(), "notify");
        vi.spyOn(api, "importPreview")
            .mockRejectedValueOnce(new Error("bad csv"))
            .mockResolvedValue({
                rows: [{ date: "2026-07-03", description: "Shop", amount: -1, duplicate: false }],
                errors: [],
            });
        const commit = vi
            .spyOn(useStore.getState(), "commitImport")
            .mockRejectedValue(new Error("offline"));
        const { user } = renderUI(<ImportDialog onClose={vi.fn()} />);
        await user.type(screen.getByPlaceholderText(/03\.07\.2026/), "broken");
        await user.click(screen.getByRole("button", { name: "Preview" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Preview failed" }),
            ),
        );
        await user.click(screen.getByRole("button", { name: "Preview" }));
        await screen.findByText("1 new");
        await user.click(screen.getByRole("button", { name: "Card" }));
        await user.click(screen.getByRole("option", { name: "Cash" }));
        expect(screen.queryByText("1 new")).not.toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Preview" }));
        await screen.findByText("1 new");
        await user.click(screen.getByRole("button", { name: "Import 1" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Import failed" }),
            ),
        );
        expect(commit).toHaveBeenCalledWith(expect.any(Array), 2);
    });
});
