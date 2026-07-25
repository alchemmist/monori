import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminSqlTab from "./AdminSqlTab.jsx";
import * as api from "../api.js";
import { renderUI, screen, waitFor, userEvent } from "../test/render.jsx";

vi.mock("../api.js");

// Mock Textarea to avoid ResizeObserver issues with autosize
vi.mock("@mantine/core", async () => {
    const mod = await vi.importActual("@mantine/core");
    return {
        ...mod,
        Textarea: ({ ref, ...props }) => {
            return <textarea ref={ref} {...props} />;
        },
    };
});

describe("AdminSqlTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        globalThis.localStorage?.clear?.();
        // Set up default mock responses
        api.api.adminSql.mockImplementation(() =>
            Promise.resolve({
                kind: "read",
                columns: [],
                rows: [],
                rowCount: 0,
                elapsedMs: 5,
                truncated: false,
            }),
        );
    });

    it("renders a textarea with SQL placeholder", () => {
        renderUI(<AdminSqlTab onClose={vi.fn()} />);
        const textarea = screen.getByLabelText("SQL statement");
        expect(textarea).toBeInTheDocument();
        expect(textarea).toHaveAttribute("placeholder", expect.stringContaining("SELECT"));
    });

    it("focuses the textarea on mount", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        const textarea = screen.getByLabelText("SQL statement");
        await waitFor(() => {
            expect(textarea).toHaveFocus();
        });
    });

    it("disables Run and Dry run buttons when SQL is empty", () => {
        renderUI(<AdminSqlTab onClose={vi.fn()} />);
        expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Dry run" })).toBeDisabled();
    });

    it("enables buttons when SQL has content", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT 1");
        expect(screen.getByRole("button", { name: "Run" })).not.toBeDisabled();
        expect(screen.getByRole("button", { name: "Dry run" })).not.toBeDisabled();
    });

    it("runs SQL query on Run button click", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: ["id", "name"],
            rows: [[1, "Alice"]],
            rowCount: 1,
            elapsedMs: 10,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT 1");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(api.api.adminSql).toHaveBeenCalledWith("SELECT 1", false, false);
        });
    });

    it("runs dry run on Dry run button click", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "dry",
            columns: [],
            rows: [],
            rowCount: 0,
            elapsedMs: 5,
            truncated: false,
            wouldWrite: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT 1");
        await user.click(screen.getByRole("button", { name: "Dry run" }));
        await waitFor(() => {
            expect(api.api.adminSql).toHaveBeenCalledWith("SELECT 1", false, true);
        });
    });

    it("runs query with Ctrl+Enter keyboard shortcut", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: [],
            rows: [],
            rowCount: 0,
            elapsedMs: 5,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT 1");
        await user.keyboard("{Control>}Enter{/Control}");
        await waitFor(() => {
            expect(api.api.adminSql).toHaveBeenCalledWith("SELECT 1", false, false);
        });
    });

    it("runs dry run with Ctrl+Shift+Enter", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "dry",
            columns: [],
            rows: [],
            rowCount: 0,
            elapsedMs: 5,
            truncated: false,
            wouldWrite: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT 1");
        await user.keyboard("{Control>}{Shift>}Enter{/Shift}{/Control}");
        await waitFor(() => {
            expect(api.api.adminSql).toHaveBeenCalledWith("SELECT 1", false, true);
        });
    });

    it("displays read query results in a table", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: ["id", "name"],
            rows: [
                [1, "Alice"],
                [2, "Bob"],
            ],
            rowCount: 2,
            elapsedMs: 15,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT * FROM users");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText("2 rows")).toBeInTheDocument();
            expect(screen.getByText("15 ms")).toBeInTheDocument();
        });
        const cells = screen.getAllByText("Alice");
        expect(cells[0]).toBeInTheDocument();
    });

    it("displays NULL values with special styling", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: ["value"],
            rows: [[null]],
            rowCount: 1,
            elapsedMs: 5,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT NULL");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText("NULL")).toBeInTheDocument();
            expect(screen.getByText("NULL")).toHaveClass("admin-muted");
        });
    });

    it("truncates long cell values", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        const longString = "a".repeat(250);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: ["data"],
            rows: [[longString]],
            rowCount: 1,
            elapsedMs: 5,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT data");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText(/^a+…$/)).toBeInTheDocument();
        });
    });

    it("shows empty table message when no rows are returned", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: ["id"],
            rows: [],
            rowCount: 0,
            elapsedMs: 5,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT * FROM empty_table");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText("No rows")).toBeInTheDocument();
        });
    });

    it("displays write result success message", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "write",
            columns: [],
            rows: [],
            rowCount: 5,
            elapsedMs: 20,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "DELETE FROM old_data");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText("5 rows affected")).toBeInTheDocument();
        });
    });

    it("handles write confirmation flow", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql
            .mockRejectedValueOnce(new Error("This write needs confirmation: 10 rows affected"))
            .mockResolvedValueOnce({
                kind: "write",
                columns: [],
                rows: [],
                rowCount: 10,
                elapsedMs: 25,
                truncated: false,
            });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "DELETE FROM data");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText(/needs confirmation/)).toBeInTheDocument();
        });
        expect(screen.getByRole("button", { name: "Apply write" })).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Apply write" }));
        await waitFor(() => {
            expect(api.api.adminSql).toHaveBeenLastCalledWith("DELETE FROM data", true, false);
        });
    });

    it("clears pending write when canceling confirmation", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockRejectedValueOnce(
            new Error("This write needs confirmation: 5 rows affected"),
        );
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "DELETE FROM data");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText(/needs confirmation/)).toBeInTheDocument();
        });
        await user.click(screen.getByRole("button", { name: "Cancel" }));
        expect(screen.queryByText(/needs confirmation/)).not.toBeInTheDocument();
    });

    it("displays error when SQL fails", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockRejectedValueOnce(new Error("Syntax error: unexpected token"));
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELEC * FROM users");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText("Syntax error: unexpected token")).toBeInTheDocument();
        });
    });

    it("clears previous error on new query", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockRejectedValueOnce(new Error("First error"));
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELEC");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText("First error")).toBeInTheDocument();
        });
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: [],
            rows: [],
            rowCount: 0,
            elapsedMs: 5,
            truncated: false,
        });
        await user.clear(textarea);
        await user.type(textarea, "SELECT 1");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.queryByText("First error")).not.toBeInTheDocument();
        });
    });

    it("shows truncated indicator when results are truncated", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: ["id"],
            rows: [[1]],
            rowCount: 1,
            elapsedMs: 30,
            truncated: true,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT * FROM huge_table");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText(/showing first 1 rows/)).toBeInTheDocument();
        });
    });

    it("displays dry run result for read query", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "dry",
            columns: [],
            rows: [],
            rowCount: 5,
            elapsedMs: 10,
            truncated: false,
            wouldWrite: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT * FROM data");
        await user.click(screen.getByRole("button", { name: "Dry run" }));
        await waitFor(() => {
            expect(screen.getByText(/Rolled back — nothing was written/)).toBeInTheDocument();
            expect(screen.getByText(/The query returned 5 rows/)).toBeInTheDocument();
        });
    });

    it("displays dry run result for would-be write", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "dry",
            columns: [],
            rows: [],
            rowCount: 3,
            elapsedMs: 15,
            truncated: false,
            wouldWrite: true,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "DELETE FROM archive");
        await user.click(screen.getByRole("button", { name: "Dry run" }));
        await waitFor(() => {
            expect(screen.getByText(/Applying this would affect 3 rows/)).toBeInTheDocument();
        });
    });

    it("stores query in history after successful run", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: [],
            rows: [],
            rowCount: 0,
            elapsedMs: 5,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT 1");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText("SELECT 1", { selector: "button" })).toBeInTheDocument();
        });
    });

    it("restores query from history", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValue({
            kind: "read",
            columns: [],
            rows: [],
            rowCount: 0,
            elapsedMs: 5,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT 1");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText("History")).toBeInTheDocument();
        });
        await user.clear(textarea);
        const historyButton = screen.getByRole("button", { name: /SELECT 1/ });
        await user.click(historyButton);
        expect(textarea).toHaveValue("SELECT 1");
    });

    it("trims whitespace from SQL before running", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: [],
            rows: [],
            rowCount: 0,
            elapsedMs: 5,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "  \n  SELECT 1  \n  ");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(api.api.adminSql).toHaveBeenCalledWith("SELECT 1", false, false);
        });
    });

    it("ignores run attempt when already busy", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockImplementation(
            () =>
                new Promise((resolve) => {
                    setTimeout(
                        () =>
                            resolve({
                                kind: "read",
                                columns: [],
                                rows: [],
                                rowCount: 0,
                                elapsedMs: 5,
                                truncated: false,
                            }),
                        100,
                    );
                }),
        );
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT 1");
        const runButton = screen.getByRole("button", { name: "Run" });
        await user.click(runButton);
        await user.click(runButton);
        await waitFor(() => {
            expect(api.api.adminSql).toHaveBeenCalledTimes(1);
        });
    });

    it("clears pending write when typing new SQL", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockRejectedValueOnce(
            new Error("This write needs confirmation: 5 rows affected"),
        );
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "DELETE FROM data");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText(/needs confirmation/)).toBeInTheDocument();
        });
        await user.clear(textarea);
        await user.type(textarea, "SELECT");
        expect(screen.queryByText(/needs confirmation/)).not.toBeInTheDocument();
    });

    it("shows row/rows singular and plural correctly", async () => {
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        api.api.adminSql.mockResolvedValueOnce({
            kind: "read",
            columns: ["id"],
            rows: [[1]],
            rowCount: 1,
            elapsedMs: 5,
            truncated: false,
        });
        const textarea = screen.getByLabelText("SQL statement");
        await user.type(textarea, "SELECT 1");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await waitFor(() => {
            expect(screen.getByText("1 row")).toBeInTheDocument();
        });
    });

    it("displays help text about keyboard shortcuts", () => {
        renderUI(<AdminSqlTab onClose={vi.fn()} />);
        expect(screen.getByText(/⌘\/Ctrl \+ Enter/)).toBeInTheDocument();
    });
});
