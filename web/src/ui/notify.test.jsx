import { describe, expect, it, vi } from "vitest";
import { notifications } from "@mantine/notifications";
import { showToast } from "./notify.js";
import { renderUI, screen } from "../test/render.jsx";

describe("showToast", () => {
    it("renders the title and content on screen", async () => {
        renderUI(<div />);
        showToast({ title: "Saved", content: "3 rows", theme: "success" });
        expect(await screen.findByText("Saved")).toBeInTheDocument();
        expect(screen.getByText("3 rows")).toBeInTheDocument();
        notifications.clean();
    });

    it("maps each gravity theme onto its Mantine colour", () => {
        const spy = vi.spyOn(notifications, "show").mockImplementation(() => "id");
        for (const [theme, color] of [
            ["danger", "red"],
            ["success", "teal"],
            ["warning", "yellow"],
            ["info", "blue"],
        ]) {
            showToast({ title: "t", theme });
            expect(spy).toHaveBeenLastCalledWith(
                expect.objectContaining({ color, autoClose: 5000 }),
            );
        }
    });

    it("falls back to grey for an unknown or missing theme, and to an empty message", () => {
        const spy = vi.spyOn(notifications, "show").mockImplementation(() => "id");
        showToast({ title: "t", theme: "chartreuse" });
        expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ color: "gray" }));
        showToast({ title: "t" });
        expect(spy).toHaveBeenLastCalledWith(
            expect.objectContaining({ color: "gray", message: "" }),
        );
    });
});
