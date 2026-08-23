import { describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import NotFound from "./NotFound.jsx";
import { renderUI, screen, within } from "../test/render.jsx";

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
    it("renders the complete receipt with separate 404 digits", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/unknown"]}>
                <NotFound />
            </MemoryRouter>,
        );

        expect(screen.getByRole("heading", { name: "404" })).toBeInTheDocument();
        expect(
            [...container.querySelectorAll<HTMLElement>(".not-found__title > span")].map(
                (digit) => digit.textContent,
            ),
        ).toEqual(["4", "0", "4"]);
        expect(screen.getByText("This page isn't in your ledger.")).toBeInTheDocument();
        expect(screen.getByText("Requested route").nextElementSibling).toHaveTextContent(
            "NOT FOUND",
        );
        expect(screen.getByText("Your balance").nextElementSibling).toHaveTextContent("still safe");
        expect(screen.getByText("Pages located").nextElementSibling).toHaveTextContent("0");
        expect(screen.getByText("Total lost").nextElementSibling).toHaveTextContent("0 ₽");
        expect(screen.getByRole("button", { name: "Go back" })).toBeInTheDocument();
    });

    it("renders every animated receipt as a branded monori scrap", () => {
        const { container } = renderUI(
            <MemoryRouter initialEntries={["/unknown"]}>
                <NotFound />
            </MemoryRouter>,
        );

        const scraps = [...container.querySelectorAll<HTMLElement>(".not-found__scrap")];
        expect(scraps).toHaveLength(4);
        for (const scrap of scraps) {
            expect(scrap).toHaveTextContent("ものり");
            expect(scrap).toHaveTextContent("404");
            expect(within(scrap).getByText("もの", { exact: false })).toBeInTheDocument();
        }
        expect(new Set(scraps.map((scrap) => scrap.style.animationDelay)).size).toBe(4);
        expect(new Set(scraps.map((scrap) => scrap.style.animationDuration)).size).toBe(4);
    });

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
        expect(screen.getByRole("link", { name: "Return to Budget" })).toHaveAttribute(
            "href",
            "/budget",
        );
    });

    it.each(["/demo", "/demo/unknown"])(
        "keeps %s inside the demo when returning to Budget",
        (path) => {
            renderUI(
                <MemoryRouter initialEntries={[path]}>
                    <NotFound />
                </MemoryRouter>,
            );

            expect(screen.getByRole("link", { name: "Go to Budget" })).toHaveAttribute(
                "href",
                "/demo/budget",
            );
            expect(screen.getByRole("link", { name: "Return to Budget" })).toHaveAttribute(
                "href",
                "/demo/budget",
            );
        },
    );

    it("replaces a direct missing route with the Budget fallback", async () => {
        const { user } = renderUI(
            <MemoryRouter initialEntries={["/unknown"]}>
                <Routes>
                    <Route path="/unknown" element={<NotFound />} />
                    <Route path="*" element={<HistoryPage />} />
                </Routes>
            </MemoryRouter>,
        );

        await user.click(screen.getByRole("button", { name: "Go back" }));
        expect(screen.getByText("/budget")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Back in test history" }));
        expect(screen.getByText("/budget")).toBeInTheDocument();
    });

    it("uses router history when a previous page exists", async () => {
        const { user } = renderUI(
            <MemoryRouter initialEntries={["/previous", "/unknown"]} initialIndex={1}>
                <Routes>
                    <Route path="/unknown" element={<NotFound />} />
                    <Route path="*" element={<HistoryPage />} />
                </Routes>
            </MemoryRouter>,
        );

        await user.click(screen.getByRole("button", { name: "Go back" }));

        expect(await screen.findByText("/previous")).toBeInTheDocument();
    });
});
