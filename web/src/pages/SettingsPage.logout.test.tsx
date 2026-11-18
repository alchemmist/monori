import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, useLocation, useNavigationType } from "react-router-dom";
import { renderUI, resetStore, screen } from "../test/render.jsx";
import { useStore } from "../store.js";
import SettingsPage from "./SettingsPage.jsx";

function CurrentRoute() {
    const location = useLocation();
    const navigationType = useNavigationType();
    return <output data-navigation-type={navigationType}>{location.pathname}</output>;
}

describe("SettingsPage logout", () => {
    afterEach(() => resetStore());

    it("replaces settings with the logout route", async () => {
        useStore.setState({ user: { id: 1, email: "me@example.com" } });
        const { user } = renderUI(
            <MemoryRouter initialEntries={["/settings"]}>
                <SettingsPage theme="light" onToggleTheme={() => {}} onMigrate={() => {}} />
                <CurrentRoute />
            </MemoryRouter>,
        );

        await user.click(screen.getByRole("button", { name: "Log out" }));

        expect(screen.getByText("/logout")).toHaveAttribute("data-navigation-type", "REPLACE");
    });
});
