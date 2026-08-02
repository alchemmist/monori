import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import NotFound from "./NotFound.jsx";
import { renderUI, screen } from "../test/render.jsx";

function HistoryPage() {
    const location = useLocation();
    const navigate = useNavigate();
    return (
        <div>
            <span>{location.pathname}</span>
            <button type="button" onClick={() => void navigate(-1)}>
                Back in test history
            </button>
        </div>
    );
}

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

    it("recognizes the demo root as part of the demo", () => {
        renderUI(
            <MemoryRouter initialEntries={["/demo"]}>
                <NotFound />
            </MemoryRouter>,
        );

        expect(screen.getByRole("link", { name: "Go to Budget" })).toHaveAttribute(
            "href",
            "/demo/budget",
        );
    });

    it("renders every animated receipt scrap", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/unknown"]}>
                <NotFound />
            </MemoryRouter>,
        );

        expect(container.querySelectorAll(".not-found__scrap")).toHaveLength(4);
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

    it("replaces the missing route with the Budget fallback", async () => {
        vi.spyOn(window.history, "length", "get").mockReturnValue(1);
        const { user } = renderUI(
            <MemoryRouter initialEntries={["/previous", "/unknown"]} initialIndex={1}>
                <Routes>
                    <Route path="/unknown" element={<NotFound />} />
                    <Route path="*" element={<HistoryPage />} />
                </Routes>
            </MemoryRouter>,
        );

        await user.click(screen.getByRole("button", { name: "Go back" }));
        expect(screen.getByText("/budget")).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Back in test history" }));
        expect(await screen.findByText("/previous")).toBeInTheDocument();
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
