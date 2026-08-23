import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { fireEvent, renderUI, resetStore, screen, setPath, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import SettingsPage from "./SettingsPage.jsx";

vi.mock("../api.js", () => ({ api: { exportXlsx: vi.fn() } }));
import { api } from "../api.js";

function renderSettings(page: ReactElement) {
    return renderUI(<MemoryRouter initialEntries={["/settings"]}>{page}</MemoryRouter>);
}

describe("SettingsPage", () => {
    afterEach(() => {
        resetStore();
        setPath("/");
    });

    it("shows account, appearance and data controls for a signed-in user", () => {
        useStore.setState({
            user: { id: 1, email: "me@example.com", createdAt: "2026-01-02", isAdmin: true },
        });
        const toggle = vi.fn();
        renderSettings(<SettingsPage theme="light" onToggleTheme={toggle} onMigrate={vi.fn()} />);
        expect(screen.getByText("me@example.com")).toBeInTheDocument();
        expect(screen.getByText("Joined 02.01.2026")).toBeInTheDocument();
        expect(screen.getByText("Admin")).toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: /migrate from spreadsheet/i }),
        ).toBeInTheDocument();
    });

    it("starts migration through its control", async () => {
        useStore.setState({ user: { id: 1, email: "me@example.com" } });
        const migrate = vi.fn();
        const { user } = renderSettings(
            <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={migrate} />,
        );
        await user.click(screen.getByRole("button", { name: /migrate from spreadsheet/i }));
        expect(migrate).toHaveBeenCalledOnce();
    });

    it("flips the theme only when the other segment is picked", async () => {
        useStore.setState({ user: { id: 1, email: "me@example.com" } });
        const toggle = vi.fn();
        const { user } = renderSettings(
            <SettingsPage theme="light" onToggleTheme={toggle} onMigrate={vi.fn()} />,
        );
        expect(screen.getByRole("radio", { name: "Light" })).toBeChecked();

        // a checked radio emits no change on click, so replay the event React would see
        const light = screen.getByRole<HTMLInputElement>("radio", { name: "Light" });
        light.checked = false;
        fireEvent.click(light);
        expect(toggle).not.toHaveBeenCalled();

        await user.click(screen.getByText("Dark"));
        expect(toggle).toHaveBeenCalledOnce();
    });

    it("shows no join date or admin badge for a plain account", () => {
        useStore.setState({ user: { id: 1, email: "plain@example.com" } });
        renderSettings(<SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />);
        expect(screen.getByText("plain@example.com")).toBeInTheDocument();
        expect(screen.queryByText("Admin")).not.toBeInTheDocument();
        expect(screen.queryByText(/^Joined/)).not.toBeInTheDocument();
    });

    it("downloads the exported workbook and reports an API error", async () => {
        useStore.setState({ user: { id: 1, email: "me@example.com" } });
        const create = vi.fn(() => "blob:test"),
            revoke = vi.fn(),
            click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
        Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
        const blob = new Blob(["xlsx"]);
        vi.mocked(api.exportXlsx).mockResolvedValueOnce(blob);
        const { user } = renderSettings(
            <SettingsPage theme="light" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />,
        );
        await user.click(screen.getByRole("button", { name: /export to excel/i }));
        await waitFor(() => expect(click).toHaveBeenCalledOnce());
        expect(create).toHaveBeenCalledExactlyOnceWith(blob);
        const anchor: unknown = click.mock.instances[0];
        expect(anchor).toBeInstanceOf(HTMLAnchorElement);
        if (!(anchor instanceof HTMLAnchorElement)) throw new Error("expected download anchor");
        expect(anchor).toHaveAttribute("download", "monori-export.xlsx");
        expect(anchor).toHaveAttribute("href", "blob:test");
        expect(anchor.isConnected).toBe(false);

        vi.mocked(api.exportXlsx).mockRejectedValueOnce(new Error("No export"));
        await user.click(screen.getByRole("button", { name: /export to excel/i }));
        expect(await screen.findByText("No export")).toBeInTheDocument();

        vi.mocked(api.exportXlsx).mockResolvedValueOnce(blob);
        await user.click(screen.getByRole("button", { name: /export to excel/i }));
        await waitFor(() => expect(screen.queryByText("No export")).not.toBeInTheDocument());
    });

    it("hides identity on the public demo", () => {
        setPath("/demo");
        renderSettings(<SettingsPage theme="dark" onToggleTheme={vi.fn()} onMigrate={vi.fn()} />);
        expect(screen.queryByText("Account")).not.toBeInTheDocument();
        expect(screen.getByText("Appearance")).toBeInTheDocument();
    });
});
