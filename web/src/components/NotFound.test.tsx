import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import NotFound from "./NotFound.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("NotFound", () => {
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
});
