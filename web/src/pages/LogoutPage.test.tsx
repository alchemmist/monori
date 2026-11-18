import { beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes, useLocation, useNavigationType } from "react-router-dom";
import { renderUI, resetStore, screen, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";
import LogoutPage from "./LogoutPage.jsx";

function Destination() {
    const location = useLocation();
    const navigationType = useNavigationType();
    return <output data-navigation-type={navigationType}>{location.pathname}</output>;
}

describe("LogoutPage", () => {
    beforeEach(() => {
        resetStore();
        localStorage.clear();
    });

    it("clears the real session and replaces itself with the welcome route", async () => {
        localStorage.setItem("monori_token", "token");
        useStore.setState({
            authChecked: true,
            user: { id: 1, email: "user@example.com" },
            tabs: [{ id: 1, key: "edit", kind: "transaction", props: {} }],
        });

        renderUI(
            <MemoryRouter initialEntries={["/logout"]}>
                <Routes>
                    <Route path="/logout" element={<LogoutPage />} />
                    <Route path="/welcome" element={<Destination />} />
                </Routes>
            </MemoryRouter>,
        );

        await waitFor(() => expect(screen.getByText("/welcome")).toBeInTheDocument());
        expect(screen.getByText("/welcome")).toHaveAttribute("data-navigation-type", "REPLACE");
        expect(useStore.getState().user).toBeNull();
        expect(useStore.getState().tabs).toEqual([]);
        expect(localStorage.getItem("monori_token")).toBeNull();
    });
});
