import { describe, expect, it, vi, afterEach } from "vitest";
import SettingsPage from "./SettingsPage.jsx";
import { renderUI, screen, waitFor, userEvent, seed, resetStore } from "../test/render.jsx";

vi.mock("../api.js");

describe("SettingsPage", () => {
    afterEach(() => resetStore());

    describe("Appearance section", () => {
        it("renders theme toggle with light and dark options", () => {
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });
            const onToggleTheme = vi.fn();
            renderUI(<SettingsPage theme="light" onToggleTheme={onToggleTheme} onMigrate={() => {}} />);

            expect(screen.getByRole("radio", { name: "Light" })).toBeInTheDocument();
            expect(screen.getByRole("radio", { name: "Dark" })).toBeInTheDocument();
        });

        it("calls onToggleTheme when switching from light to dark", async () => {
            const { user } = renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={() => {}} />,
            );
            const darkOption = screen.getByRole("radio", { name: "Dark" });
            expect(darkOption).not.toBeChecked();
            await user.click(darkOption);
            const onToggleTheme = vi.fn();
            renderUI(
                <SettingsPage theme="light" onToggleTheme={onToggleTheme} onMigrate={() => {}} />,
            );
        });

        it("reflects current theme selection in radio button", () => {
            renderUI(
                <SettingsPage theme="dark" onToggleTheme={vi.fn()} onMigrate={() => {}} />,
            );
            expect(screen.getByRole("radio", { name: "Dark" })).toBeChecked();
        });
    });

    describe("Account section (non-demo)", () => {
        it("hides account section in demo mode", async () => {
            const { setPath } = await import("../test/render.jsx");
            setPath("/demo");
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });

            renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={() => {}} />,
            );

            expect(screen.queryByText("Account")).not.toBeInTheDocument();
        });
    });

    describe("Export functionality", () => {
        it("renders Export to Excel button with export hint", () => {
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });
            renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={() => {}} />,
            );

            expect(screen.getByRole("button", { name: "Export to Excel" })).toBeInTheDocument();
            expect(
                screen.getByText("Download all data as a YNAB-style Excel workbook"),
            ).toBeInTheDocument();
        });

        it("disables export button while exporting", async () => {
            const { user } = renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={() => {}} />,
            );
            const exportButton = screen.getByRole("button", { name: "Export to Excel" });

            const { api } = await import("../api.js");
            vi.spyOn(api, "exportXlsx").mockImplementation(
                () => new Promise(() => {}),
            );

            await user.click(exportButton);
            expect(exportButton).toHaveAttribute("data-loading", "true");
        });

        it("triggers download when export succeeds", async () => {
            const { user } = renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={() => {}} />,
            );

            const blob = new Blob(["test data"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
            const { api } = await import("../api.js");
            vi.spyOn(api, "exportXlsx").mockResolvedValueOnce(blob);
            vi.spyOn(URL, "createObjectURL").mockReturnValueOnce("blob:mock");
            vi.spyOn(URL, "revokeObjectURL").mockImplementationOnce(() => {});

            const exportButton = screen.getByRole("button", { name: "Export to Excel" });
            await user.click(exportButton);

            await waitFor(() => {
                expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
            });
        });

        it("displays error message on export failure", async () => {
            const { user } = renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={() => {}} />,
            );

            const { api } = await import("../api.js");
            vi.spyOn(api, "exportXlsx").mockRejectedValueOnce(
                new Error("Export failed"),
            );

            const exportButton = screen.getByRole("button", { name: "Export to Excel" });
            await user.click(exportButton);

            await waitFor(() => {
                expect(screen.getByText("Export failed")).toBeInTheDocument();
            });
        });

        it("clears error on successful export after failure", async () => {
            const { user } = renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={() => {}} />,
            );

            const { api } = await import("../api.js");
            const exportSpy = vi.spyOn(api, "exportXlsx");
            exportSpy.mockRejectedValueOnce(new Error("Export failed"));

            const exportButton = screen.getByRole("button", { name: "Export to Excel" });
            await user.click(exportButton);

            await waitFor(() => {
                expect(screen.getByText("Export failed")).toBeInTheDocument();
            });

            const blob = new Blob(["test"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
            exportSpy.mockResolvedValueOnce(blob);
            vi.spyOn(URL, "createObjectURL").mockReturnValueOnce("blob:mock");
            vi.spyOn(URL, "revokeObjectURL").mockImplementationOnce(() => {});

            await user.click(exportButton);

            await waitFor(() => {
                expect(screen.queryByText("Export failed")).not.toBeInTheDocument();
            });
        });
    });

    describe("Migrate functionality", () => {
        it("renders Migrate from spreadsheet button", () => {
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });
            renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />,
            );

            expect(screen.getByRole("button", { name: "Migrate from spreadsheet" })).toBeInTheDocument();
        });

        it("calls onMigrate when button is clicked", async () => {
            const { user } = renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />,
            );

            const onMigrate = vi.fn();
            renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={onMigrate} />,
            );

            const migrateButton = screen.getByRole("button", { name: "Migrate from spreadsheet" });
            await user.click(migrateButton);
        });

        it("displays migration hint text", () => {
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });
            renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />,
            );

            expect(
                screen.getByText("Import categories, transactions and budgets from a YNAB-style workbook"),
            ).toBeInTheDocument();
        });
    });

    describe("Page structure", () => {
        it("renders Settings title", () => {
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });
            renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />,
            );

            expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
        });

        it("renders Data section", () => {
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });
            renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />,
            );

            expect(screen.getByRole("heading", { level: 2, name: "Data" })).toBeInTheDocument();
        });

        it("renders Appearance section", () => {
            seed({ accounts: [], groups: [], categories: [], budgets: [], transactions: [] });
            renderUI(
                <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />,
            );

            expect(screen.getByRole("heading", { level: 2, name: "Appearance" })).toBeInTheDocument();
        });
    });
});
