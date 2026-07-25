import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import ImportDialog from "./ImportDialog.jsx";
import {
    renderUI,
    resetStore,
    seed,
    screen,
    waitFor,
} from "../test/render.jsx";

vi.mock("../api.js", () => ({
    api: {
        importPreview: vi.fn(),
    },
}));

describe("ImportDialog", () => {
    beforeEach(() => {
        resetStore();
        vi.clearAllMocks();
        localStorage.clear();
    });

    afterEach(() => {
        localStorage.clear();
    });

    it("renders the import dialog", () => {
        seed({ accounts: [{ id: 1, name: "Card", archived: false }] });
        const onClose = vi.fn();

        renderUI(<ImportDialog onClose={onClose} />);

        expect(screen.getByText("Import bank statement")).toBeInTheDocument();
        expect(screen.getByText("Upload bank CSV")).toBeInTheDocument();
    });

    it("shows account selector with active accounts only", () => {
        seed({
            accounts: [
                { id: 1, name: "Card", archived: false },
                { id: 2, name: "Old Account", archived: true },
            ],
        });
        const onClose = vi.fn();

        renderUI(<ImportDialog onClose={onClose} />);

        expect(screen.queryByText("Old Account")).not.toBeInTheDocument();
        expect(screen.getByText("Card")).toBeInTheDocument();
    });

    it("preselects first active account", () => {
        seed({
            accounts: [
                { id: 1, name: "Card", archived: false },
                { id: 2, name: "Cash", archived: false },
            ],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const combobox = screen.getByRole("combobox");
        expect(combobox).toHaveValue("1");
    });

    it("restores last selected account from localStorage", () => {
        localStorage.setItem("import_last_account", "2");

        seed({
            accounts: [
                { id: 1, name: "Card", archived: false },
                { id: 2, name: "Cash", archived: false },
            ],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const combobox = screen.getByRole("combobox");
        expect(combobox).toHaveValue("2");
    });

    it("ignores invalid stored account from localStorage", () => {
        localStorage.setItem("import_last_account", "999");

        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const combobox = screen.getByRole("combobox");
        expect(combobox).toHaveValue("1");
    });

    it("shows file upload input", () => {
        seed({ accounts: [{ id: 1, name: "Card", archived: false }] });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const fileInput = document.querySelector('input[type="file"]');
        expect(fileInput).toHaveAttribute("accept", ".csv,text/csv");
    });

    it("shows paste area for statement rows", () => {
        seed({ accounts: [{ id: 1, name: "Card", archived: false }] });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        expect(textarea).toBeInTheDocument();
    });

    it("allows typing statement text in textarea", async () => {
        const { user } = renderUI(null);
        seed({ accounts: [{ id: 1, name: "Card", archived: false }] });
        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        const testText = "03.07.2026\t100.00";
        await user.click(textarea);
        await user.type(textarea, testText);

        expect(textarea).toHaveValue(testText);
    });

    it("Preview button is disabled when no text", () => {
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        renderUI(<ImportDialog onClose={vi.fn()} />);

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        expect(previewBtn).toBeDisabled();
    });

    it("Preview button is enabled when text and account are set", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "some data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        expect(previewBtn).not.toBeDisabled();
    });

    it("calls API preview when Preview is clicked", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [
                {
                    date: "2026-03-05",
                    description: "Test",
                    amount: -1000,
                    card: "*1234",
                    categoryId: 2,
                    duplicate: false,
                },
            ],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "03.07.2026\t-1000");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(api.importPreview).toHaveBeenCalledWith("03.07.2026\t-1000", 1);
        });
    });

    it("shows preview with new and duplicate counts", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [
                {
                    date: "2026-03-05",
                    description: "New",
                    amount: -1000,
                    duplicate: false,
                    categoryId: 2,
                },
                {
                    date: "2026-03-04",
                    description: "Duplicate",
                    amount: -500,
                    duplicate: true,
                    categoryId: 2,
                },
            ],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "test data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(screen.getByText("1 new")).toBeInTheDocument();
            expect(screen.getByText("1 duplicates skipped")).toBeInTheDocument();
        });
    });

    it("shows error count in preview", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [],
            errors: [{ line: 1, error: "Invalid format" }],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "bad data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(screen.getByText("1 unparsed lines")).toBeInTheDocument();
        });
    });

    it("displays preview table with transaction data", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [
                {
                    date: "2026-03-05",
                    description: "Coffee shop",
                    amount: -50000,
                    duplicate: false,
                    categoryId: 2,
                },
            ],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(screen.getByText("05.03.2026")).toBeInTheDocument();
            expect(screen.getByText("Coffee shop")).toBeInTheDocument();
        });
    });

    it("marks duplicate rows with reduced opacity", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [
                {
                    date: "2026-03-05",
                    description: "Duplicate",
                    amount: -1000,
                    duplicate: true,
                    categoryId: 2,
                },
            ],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            const rows = screen.getAllByRole("row");
            const duplicateRow = rows.find((r) => r.textContent.includes("Duplicate"));
            expect(duplicateRow).toHaveStyle({ opacity: "0.4" });
        });
    });

    it("shows category name for categorized rows", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [
                {
                    date: "2026-03-05",
                    description: "Groceries",
                    amount: -1000,
                    duplicate: false,
                    categoryId: 2,
                },
            ],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(screen.getByText("Groceries")).toBeInTheDocument();
        });
    });

    it("shows uncategorized for rows without category", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [
                {
                    date: "2026-03-05",
                    description: "Unknown",
                    amount: -1000,
                    duplicate: false,
                    categoryId: null,
                },
            ],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(screen.getByText("uncategorized")).toBeInTheDocument();
        });
    });

    it("changes to Import button in preview with count", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [
                {
                    date: "2026-03-05",
                    description: "Test",
                    amount: -1000,
                    duplicate: false,
                    categoryId: 2,
                },
            ],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            const importBtn = screen.getByRole("button", { name: "Import 1" });
            expect(importBtn).toBeInTheDocument();
        });
    });

    it("disables Import when no new rows", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [
                {
                    date: "2026-03-05",
                    description: "Duplicate",
                    amount: -1000,
                    duplicate: true,
                    categoryId: 2,
                },
            ],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            const importBtn = screen.getByRole("button", { name: "Import 0" });
            expect(importBtn).toBeDisabled();
        });
    });

    it("Back button returns to input when in preview", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(screen.getByText("0 new")).toBeInTheDocument();
        });

        const backBtn = screen.getByRole("button", { name: "Back" });
        await user.click(backBtn);

        await waitFor(() => {
            expect(screen.queryByText("0 new")).not.toBeInTheDocument();
        });
    });

    it("shows error when preview fails", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockRejectedValue(new Error("Invalid format"));

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "bad data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(screen.getByText("Preview failed")).toBeInTheDocument();
        });
    });

    it("Cancel button closes from input state", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const onClose = vi.fn();

        renderUI(<ImportDialog onClose={onClose} />);

        const cancelBtn = screen.getByRole("button", { name: "Cancel" });
        await user.click(cancelBtn);

        expect(onClose).toHaveBeenCalled();
    });

    it("shows error details up to 5 lines", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [],
            errors: [
                { line: 1, error: "Error 1" },
                { line: 2, error: "Error 2" },
            ],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "bad");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(screen.getByText("line 1: Error 1")).toBeInTheDocument();
            expect(screen.getByText("line 2: Error 2")).toBeInTheDocument();
        });
    });

    it("switches account when selecting different one", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [
                { id: 1, name: "Card", archived: false },
                { id: 2, name: "Cash", archived: false },
            ],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const combobox = screen.getByRole("combobox");
        await user.selectOptions(combobox, "2");

        expect(combobox).toHaveValue("2");
    });

    it("shows remember card tail checkbox when tail can be bound", async () => {
        const { user } = renderUI(null);
        seed({
            accounts: [{ id: 1, name: "Card", archived: false, cardTails: [] }],
        });
        const { api } = require("../api.js");
        api.importPreview.mockResolvedValue({
            rows: [
                {
                    date: "2026-03-05",
                    description: "Test",
                    amount: -1000,
                    duplicate: false,
                    categoryId: 2,
                    card: "*1234",
                },
            ],
            errors: [],
        });

        renderUI(<ImportDialog onClose={vi.fn()} />);

        const textarea = screen.getByPlaceholderText(/03.07.2026/);
        await user.click(textarea);
        await user.type(textarea, "data");

        const previewBtn = screen.getByRole("button", { name: "Preview" });
        await user.click(previewBtn);

        await waitFor(() => {
            expect(screen.getByText(/Remember card \*1234 for Card/)).toBeInTheDocument();
        });
    });
});
