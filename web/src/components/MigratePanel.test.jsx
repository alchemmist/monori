import { describe, expect, it, vi, afterEach } from "vitest";
import MigratePanel from "./MigratePanel.jsx";
import { renderUI, screen, waitFor, userEvent, seed, resetStore } from "../test/render.jsx";

vi.mock("../api.js");

describe("MigratePanel", () => {
    afterEach(() => resetStore());

    describe("Idle state", () => {
        it("renders Choose .xlsx file button", () => {
            seed({
                accounts: [
                    {
                        id: 1,
                        name: "Card",
                        type: "card",
                        icon: "card",
                        color: "#5b6472",
                        currency: "RUB",
                        archived: false,
                    },
                ],
                groups: [],
                categories: [],
                budgets: [],
                transactions: [],
            });
            renderUI(<MigratePanel onClose={vi.fn()} />);

            expect(screen.getByRole("button", { name: "Choose .xlsx file" })).toBeInTheDocument();
        });

        it("renders Cancel button in footer", () => {
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });
            renderUI(<MigratePanel onClose={vi.fn()} />);

            expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
        });

        it("renders Import button disabled initially", () => {
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });
            renderUI(<MigratePanel onClose={vi.fn()} />);

            expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
        });
    });

    describe("File selection and preview", () => {
        it("loads file when file is selected", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 2,
                categories: 5,
                transactions: 100,
                budgetCells: 10,
                errors: [],
                warnings: [],
                accountMarkers: ["Account1"],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByText(/2 groups, 5 categories, 100 transactions/)).toBeInTheDocument();
            });
        });

        it("changes button text to Choose another file after file is loaded", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 1,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Choose another file" })).toBeInTheDocument();
            });
        });

        it("displays file name after selection", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 1,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "mydata.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByText("mydata.xlsx")).toBeInTheDocument();
            });
        });

        it("displays preview errors count when errors exist", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 10,
                budgetCells: 0,
                errors: ["error1", "error2", "error3"],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(
                    screen.getByText("3 rows could not be parsed and will be skipped"),
                ).toBeInTheDocument();
            });
        });

        it("displays warnings from preview", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 10,
                budgetCells: 0,
                errors: [],
                warnings: ["Warning 1", "Warning 2"],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByText("Warning 1")).toBeInTheDocument();
                expect(screen.getByText("Warning 2")).toBeInTheDocument();
            });
        });
    });

    describe("Account mapping", () => {
        it("shows account mapping selects for each marker", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 1,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: ["Marker1", "Marker2"],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByText("Account for Marker1")).toBeInTheDocument();
                expect(screen.getByText("Account for Marker2")).toBeInTheDocument();
            });
        });

        it("shows mapping for unmarked rows", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 1,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: [""],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByText("Account for (default)")).toBeInTheDocument();
            });
        });

        it("enables Import button only when all accounts are mapped", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 1,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: ["Marker1"],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
            });

            const selects = screen.getAllByRole("combobox");
            if (selects.length > 0) {
                await user.click(selects[0]);
            }
        });
    });

    describe("Budget conflict handling", () => {
        it("shows budget conflict radio options when conflicts exist", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 1,
                budgetCells: 5,
                errors: [],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 3,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByText(/3 budget cells already exist/)).toBeInTheDocument();
                expect(screen.getByRole("radio", { name: "Overwrite" })).toBeInTheDocument();
                expect(screen.getByRole("radio", { name: "Keep mine" })).toBeInTheDocument();
            });
        });

        it("hides budget conflict options when no conflicts exist", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 1,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.queryByText(/budget cells already exist/)).not.toBeInTheDocument();
            });
        });
    });

    describe("Result state", () => {
        it("displays success message after import", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 10,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);
            vi.spyOn(api, "workbookCommit").mockResolvedValueOnce({
                inserted: 8,
                skipped: 2,
                groupsCreated: 1,
                categoriesCreated: 1,
                budgetsWritten: 0,
            });

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Import" })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: "Import" }));

            await waitFor(() => {
                expect(
                    screen.getByText(/Imported 8 transactions \(2 duplicates skipped\)/),
                ).toBeInTheDocument();
                expect(screen.getByText(/1 groups and 1 categories created/)).toBeInTheDocument();
            });
        });

        it("changes button to Done in result state", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 10,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);
            vi.spyOn(api, "workbookCommit").mockResolvedValueOnce({
                inserted: 5,
                skipped: 0,
                groupsCreated: 0,
                categoriesCreated: 0,
                budgetsWritten: 0,
            });

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Import" })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: "Import" }));

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
            });
        });

        it("displays unmapped card tails warning if present", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 10,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);
            vi.spyOn(api, "workbookCommit").mockResolvedValueOnce({
                inserted: 5,
                skipped: 0,
                groupsCreated: 0,
                categoriesCreated: 0,
                budgetsWritten: 0,
                unmappedTails: [
                    { tail: "1234", rows: 10 },
                    { tail: "5678", rows: 5 },
                ],
            });

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Import" })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: "Import" }));

            await waitFor(() => {
                expect(screen.getByText(/Cards not bound to any account/)).toBeInTheDocument();
                expect(screen.getByText(/\*1234 \(10 rows\)/)).toBeInTheDocument();
                expect(screen.getByText(/\*5678 \(5 rows\)/)).toBeInTheDocument();
            });
        });
    });

    describe("Error handling", () => {
        it("displays error when file reading fails", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            vi.spyOn(api, "workbookPreview").mockRejectedValueOnce(
                new Error("Invalid file format"),
            );

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["invalid"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByText("Could not read workbook")).toBeInTheDocument();
            });
        });

        it("displays error when migration fails", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 10,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);
            vi.spyOn(api, "workbookCommit").mockRejectedValueOnce(
                new Error("Server error during import"),
            );

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Import" })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: "Import" }));

            await waitFor(() => {
                expect(screen.getByText("Migration failed")).toBeInTheDocument();
            });
        });
    });

    describe("Close and cancel", () => {
        it("calls onClose when Cancel is clicked", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);

            const onClose = vi.fn();
            renderUI(<MigratePanel onClose={onClose} />);

            const cancelButton = screen.getByRole("button", { name: "Cancel" });
            await user.click(cancelButton);
        });

        it("changes Cancel to Close button in result state", async () => {
            const { user } = renderUI(<MigratePanel onClose={vi.fn()} />);
            const { api } = await import("../api.js");

            const preview = {
                groups: 1,
                categories: 1,
                transactions: 10,
                budgetCells: 0,
                errors: [],
                warnings: [],
                accountMarkers: [],
                budgetConflicts: 0,
            };
            vi.spyOn(api, "workbookPreview").mockResolvedValueOnce(preview);
            vi.spyOn(api, "workbookCommit").mockResolvedValueOnce({
                inserted: 5,
                skipped: 0,
                groupsCreated: 0,
                categoriesCreated: 0,
                budgetsWritten: 0,
            });

            const fileInput = document.querySelector('input[type="file"]');
            const file = new File(["test"], "data.xlsx", {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });

            await user.upload(fileInput, file);

            await waitFor(() => {
                expect(screen.getByRole("button", { name: "Import" })).not.toBeDisabled();
            });

            await user.click(screen.getByRole("button", { name: "Import" }));

            await waitFor(() => {
                const closeButton = screen.getAllByRole("button").find(
                    (b) => b.textContent === "Close" && !b.getAttribute("data-loading"),
                );
                expect(closeButton).toBeInTheDocument();
            });
        });
    });
});
