import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import NotFound from "./NotFound.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("NotFound", () => {
    afterEach(() => vi.restoreAllMocks());

    it("returns app users to the app Budget", () => {
        renderUI(
            <MemoryRouter initialEntries={["/unknown"]}>
                <NotFound />
            </MemoryRouter>,
        );

        expect(screen.getByRole("link", { name: "Go to Budget" })).toHaveAttribute(
            "href",
            "/budget",
        );
    });

    it("keeps demo users inside the demo when returning to Budget", () => {
        renderUI(
            <MemoryRouter initialEntries={["/demo/unknown"]}>
                <NotFound />
            </MemoryRouter>,
        );

        expect(screen.getByRole("link", { name: "Go to Budget" })).toHaveAttribute(
            "href",
            "/demo/budget",
        );
        expect(screen.getByRole("link", { name: "Go to Budget" })).toHaveAccessibleName(
            "Go to Budget",
        );
    });

    it("returns to Budget when there is no browser history", async () => {
        vi.spyOn(window.history, "length", "get").mockReturnValue(1);
        const { user } = renderUI(
            <MemoryRouter initialEntries={["/unknown"]}>
                <Routes>
                    <Route path="/unknown" element={<NotFound />} />
                    <Route path="/budget" element={<div>Budget page</div>} />
                </Routes>
            </MemoryRouter>,
        );

        await user.click(screen.getByRole("button", { name: "Go back" }));

        expect(screen.getByText("Budget page")).toBeInTheDocument();
    });

    it("uses browser history when a previous page exists", async () => {
        vi.spyOn(window.history, "length", "get").mockReturnValue(2);
        const back = vi.spyOn(window.history, "back").mockImplementation(() => {});
        const { user } = renderUI(
            <MemoryRouter initialEntries={["/unknown"]}>
                <NotFound />
            </MemoryRouter>,
        );

        await user.click(screen.getByRole("button", { name: "Go back" }));

        expect(back).toHaveBeenCalledOnce();
    });
});
