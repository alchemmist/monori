import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderUI, resetStore, screen, seed, waitFor } from "../test/render.jsx";
import { api } from "../api.js";
import { useStore } from "../store.js";
import ImportPanel from "./ImportPanel.jsx";

const csv = (name = "statement.csv") => new File(["date,amount\n"], name, { type: "text/csv" });

const upload = (container, file = csv()) =>
    fireEvent.change(container.querySelector('input[type="file"]'), {
        target: { files: [file] },
    });

const accounts = [
    { id: 1, name: "Card", archived: false },
    { id: 2, name: "Cash", archived: false },
];

describe("ImportPanel", () => {
    beforeEach(() => {
        resetStore();
        seed({ accounts });
        vi.clearAllMocks();
        globalThis.localStorage?.clear?.();
        window.visualViewport ??= { addEventListener: () => {}, removeEventListener: () => {} };
        document.fonts ??= { addEventListener: () => {}, removeEventListener: () => {} };
    });

    it("shows the empty prompt before any file is chosen", () => {
        const { container } = renderUI(<ImportPanel onClose={vi.fn()} />);
        expect(screen.getByText(/Upload a bank CSV\./)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Upload bank CSV" })).toBeInTheDocument();
        expect(container.querySelector('input[type="file"]')).toBeInTheDocument();
    });

    it("clicking the upload button opens the hidden file input", async () => {
        const { container, user } = renderUI(<ImportPanel onClose={vi.fn()} />);
        const input = container.querySelector('input[type="file"]');
        const click = vi.spyOn(input, "click");
        await user.click(screen.getByRole("button", { name: "Upload bank CSV" }));
        expect(click).toHaveBeenCalled();
    });

    it("previews an uploaded statement, imports the fresh rows and closes", async () => {
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "*2947",
                    description: "Coffee",
                    amount: -45000,
                    accountId: 1,
                    categoryId: 2,
                    duplicate: false,
                },
                {
                    date: "2026-07-02",
                    card: "*2947",
                    description: "Old",
                    amount: -100,
                    accountId: 1,
                    categoryId: null,
                    duplicate: true,
                },
            ],
            errors: [],
        });
        const commit = vi
            .spyOn(useStore.getState(), "commitImport")
            .mockResolvedValue({ inserted: 1 });
        const close = vi.fn();
        const { container } = renderUI(<ImportPanel onClose={close} />);

        upload(container, csv("july.csv"));
        await waitFor(() => expect(api.importPreview).toHaveBeenCalledWith("date,amount\n"));
        expect(await screen.findByText("july.csv")).toBeInTheDocument();
        expect(screen.getByText("1 new")).toBeInTheDocument();
        expect(screen.getByText("1 duplicates skipped")).toBeInTheDocument();
        expect(screen.getByText("Coffee")).toBeInTheDocument();

        const importButton = screen.getByRole("button", { name: "Import 1" });
        expect(importButton).toBeEnabled();
        fireEvent.click(importButton);
        await waitFor(() =>
            expect(commit).toHaveBeenCalledWith([
                expect.objectContaining({ description: "Coffee" }),
            ]),
        );
        await waitFor(() => expect(close).toHaveBeenCalled());
    });

    it("blocks import until every row has an account and re-checks duplicates on change", async () => {
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "",
                    description: "Shop",
                    amount: -500,
                    accountId: null,
                    categoryId: null,
                    duplicate: false,
                },
            ],
            errors: [],
        });
        const dups = vi.spyOn(api, "importDuplicates").mockResolvedValue({ duplicates: [false] });
        const commit = vi
            .spyOn(useStore.getState(), "commitImport")
            .mockResolvedValue({ inserted: 1 });
        const { container, user } = renderUI(<ImportPanel onClose={vi.fn()} />);

        upload(container);
        await screen.findByText("Shop");
        expect(screen.getByText("1 need an account")).toBeInTheDocument();
        expect(screen.getByText(/Choose an account for every unassigned row/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Import 1" })).toBeDisabled();
        expect(screen.getByText("—")).toBeInTheDocument();

        const accountSelect = screen.getByRole("button", { name: "Choose account" });
        await user.click(accountSelect);
        await user.click(await screen.findByRole("option", { name: "Cash" }));
        await waitFor(() =>
            expect(dups).toHaveBeenCalledWith([
                expect.objectContaining({ accountId: 2, description: "Shop" }),
            ]),
        );
        await waitFor(() =>
            expect(screen.queryByText("1 need an account")).not.toBeInTheDocument(),
        );

        const importButton = screen.getByRole("button", { name: "Import 1" });
        await waitFor(() => expect(importButton).toBeEnabled());
        fireEvent.click(importButton);
        await waitFor(() => expect(commit).toHaveBeenCalled());
    });

    it("lets the user change a row's category", async () => {
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "",
                    description: "Shop",
                    amount: -500,
                    accountId: 1,
                    categoryId: null,
                    duplicate: false,
                },
            ],
            errors: [],
        });
        const { container, user } = renderUI(<ImportPanel onClose={vi.fn()} />);
        upload(container);
        await screen.findByText("Shop");

        const categorySelect = screen.getByRole("button", { name: "Uncategorized" });
        await user.click(categorySelect);
        await user.click(await screen.findByRole("option", { name: "Groceries" }));
        expect(screen.getByRole("button", { name: "Groceries" })).toBeInTheDocument();
    });

    it("offers income and expense categories for positive amounts", async () => {
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "",
                    description: "Paycheck",
                    amount: 90000,
                    accountId: 1,
                    categoryId: null,
                    duplicate: false,
                },
            ],
            errors: [],
        });
        const { container, user } = renderUI(<ImportPanel onClose={vi.fn()} />);
        upload(container);
        await screen.findByText("Paycheck");

        await user.click(screen.getByRole("button", { name: "Uncategorized" }));
        expect(await screen.findByRole("option", { name: "Salary" })).toBeInTheDocument();
        expect(screen.getByRole("option", { name: "Groceries" })).toBeInTheDocument();
    });

    it("renders unparsed lines and their per-line detail", async () => {
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "",
                    description: "Shop",
                    amount: -1,
                    accountId: 1,
                    categoryId: null,
                    duplicate: false,
                },
            ],
            errors: [{ line: 4, error: "bad date" }],
        });
        const { container } = renderUI(<ImportPanel onClose={vi.fn()} />);
        upload(container);
        expect(await screen.findByText("1 unparsed lines")).toBeInTheDocument();
        expect(screen.getByText("line 4: bad date")).toBeInTheDocument();
    });

    it("reports a preview failure with a toast and keeps the empty state", async () => {
        vi.spyOn(api, "importPreview").mockRejectedValue(new Error("bad csv"));
        const notify = vi.spyOn(useStore.getState(), "notify");
        const { container } = renderUI(<ImportPanel onClose={vi.fn()} />);
        upload(container);
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Preview failed" }),
            ),
        );
        expect(screen.getByText(/Upload a bank CSV\./)).toBeInTheDocument();
    });

    it("reports a file that cannot be read", async () => {
        const notify = vi.spyOn(useStore.getState(), "notify");
        const preview = vi.spyOn(api, "importPreview");
        const { container } = renderUI(<ImportPanel onClose={vi.fn()} />);
        upload(container, new File([], "empty.csv"));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Could not read the file" }),
            ),
        );
        expect(preview).not.toHaveBeenCalled();
    });

    it("ignores an empty file selection", () => {
        const preview = vi.spyOn(api, "importPreview");
        const { container } = renderUI(<ImportPanel onClose={vi.fn()} />);
        fireEvent.change(container.querySelector('input[type="file"]'), {
            target: { files: [] },
        });
        expect(preview).not.toHaveBeenCalled();
    });

    it("reports a duplicate-check failure with a toast", async () => {
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "",
                    description: "Shop",
                    amount: -500,
                    accountId: 1,
                    categoryId: null,
                    duplicate: false,
                },
            ],
            errors: [],
        });
        vi.spyOn(api, "importDuplicates").mockRejectedValue(new Error("offline"));
        const notify = vi.spyOn(useStore.getState(), "notify");
        const { container, user } = renderUI(<ImportPanel onClose={vi.fn()} />);
        upload(container);
        await screen.findByText("Shop");
        await user.click(screen.getByRole("button", { name: "Card" }));
        await user.click(await screen.findByRole("option", { name: "Cash" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Could not check duplicates" }),
            ),
        );
    });

    it("reports a commit failure with a toast and stays open", async () => {
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "",
                    description: "Shop",
                    amount: -500,
                    accountId: 1,
                    categoryId: null,
                    duplicate: false,
                },
            ],
            errors: [],
        });
        vi.spyOn(useStore.getState(), "commitImport").mockRejectedValue(new Error("boom"));
        const notify = vi.spyOn(useStore.getState(), "notify");
        const close = vi.fn();
        const { container } = renderUI(<ImportPanel onClose={close} />);
        upload(container);
        await screen.findByText("Shop");
        fireEvent.click(screen.getByRole("button", { name: "Import 1" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Import failed" }),
            ),
        );
        expect(close).not.toHaveBeenCalled();
    });

    it("closes without importing when Cancel is clicked", async () => {
        const close = vi.fn();
        const { user } = renderUI(<ImportPanel onClose={close} />);
        await user.click(screen.getByRole("button", { name: "Cancel" }));
        expect(close).toHaveBeenCalled();
    });

    it("lets the user pick another CSV after a first upload", async () => {
        vi.spyOn(api, "importPreview").mockResolvedValue({
            rows: [
                {
                    date: "2026-07-03",
                    card: "",
                    description: "Shop",
                    amount: -1,
                    accountId: 1,
                    categoryId: null,
                    duplicate: false,
                },
            ],
            errors: [],
        });
        const { container } = renderUI(<ImportPanel onClose={vi.fn()} />);
        upload(container, csv("first.csv"));
        await screen.findByText("first.csv");
        expect(screen.getByRole("button", { name: "Choose another CSV" })).toBeInTheDocument();
    });
});
