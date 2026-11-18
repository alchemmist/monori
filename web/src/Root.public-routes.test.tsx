import { afterEach, describe, expect, it } from "vitest";
import Root from "./Root.jsx";
import { useStore } from "./store.js";
import { renderUI, resetStore, screen, setPath, waitFor } from "./test/render.jsx";

describe("Root public routes", () => {
    afterEach(() => {
        resetStore();
        localStorage.clear();
        setPath("/");
    });

    it("renders the real NotFound component for an unknown URL", async () => {
        setPath("/somewhere/over-the-ledger");

        renderUI(<Root />);

        expect(await screen.findByRole("heading", { name: "404" })).toBeInTheDocument();
        expect(screen.getByText("This page isn't in your ledger.")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Return to Budget" })).toHaveAttribute(
            "href",
            "/budget",
        );
    });

    it("runs the real logout page before redirecting to welcome", async () => {
        localStorage.setItem("monori_token", "token");
        useStore.setState({
            authChecked: true,
            user: { id: 1, email: "user@example.com" },
        });
        setPath("/logout");

        renderUI(<Root />);

        await waitFor(() => expect(window.location.pathname).toBe("/welcome"));
        expect(useStore.getState().user).toBeNull();
        expect(localStorage.getItem("monori_token")).toBeNull();
    });
});
