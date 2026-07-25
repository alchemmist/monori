import { afterEach, describe, expect, it, vi } from "vitest";
import { renderUI, resetStore, screen, setPath, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import SettingsPage from "./SettingsPage.jsx";

vi.mock("../api.js", () => ({ api: { exportXlsx: vi.fn() } }));
import { api } from "../api.js";

describe("SettingsPage", () => {
    afterEach(() => { resetStore(); setPath("/"); });

    it("shows account, appearance and data controls for a signed-in user", () => {
        useStore.setState({ user: { email: "me@example.com", createdAt: "2026-01-02", isAdmin: true } });
        const toggle = vi.fn();
        renderUI(<SettingsPage theme="light" onToggleTheme={toggle} onMigrate={vi.fn()} />);
        expect(screen.getByText("me@example.com")).toBeInTheDocument();
        expect(screen.getByText("Joined 02.01.2026")).toBeInTheDocument();
        expect(screen.getByText("Admin")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /migrate from spreadsheet/i })).toBeInTheDocument();
    });

    it("toggles theme, migrates and logs out through their controls", async () => {
        useStore.setState({ user: { email: "me@example.com" } });
        const toggle = vi.fn(), migrate = vi.fn(), logout = vi.spyOn(useStore.getState(), "logout").mockImplementation(() => {});
        const { user } = renderUI(<SettingsPage theme="light" onToggleTheme={toggle} onMigrate={migrate} />);
        await user.click(screen.getByText("Dark"));
        await user.click(screen.getByRole("button", { name: /migrate from spreadsheet/i }));
        await user.click(screen.getByRole("button", { name: /log out/i }));
        expect(toggle).toHaveBeenCalled();
        expect(migrate).toHaveBeenCalled();
        expect(logout).toHaveBeenCalled();
    });

    it("downloads the exported workbook and reports an API error", async () => {
        useStore.setState({ user: { email: "me@example.com" } });
        const create = vi.fn(() => "blob:test"), revoke = vi.fn(), click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
        Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
        api.exportXlsx.mockResolvedValueOnce(new Blob(["xlsx"]));
        const { user } = renderUI(<SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />);
        await user.click(screen.getByRole("button", { name: /export to excel/i }));
        await waitFor(() => expect(click).toHaveBeenCalled());
        api.exportXlsx.mockRejectedValueOnce(new Error("No export"));
        await user.click(screen.getByRole("button", { name: /export to excel/i }));
        expect(await screen.findByText("No export")).toBeInTheDocument();
    });

    it("hides identity on the public demo", () => {
        setPath("/demo");
        renderUI(<SettingsPage theme="dark" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />);
        expect(screen.queryByText("Account")).not.toBeInTheDocument();
        expect(screen.getByText("Appearance")).toBeInTheDocument();
    });
});
