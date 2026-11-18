import { describe, expect, it } from "vitest";
import Wordmark from "./Wordmark.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("Wordmark", () => {
    // the mark is kana, so screen readers need the latin name spelled out
    it("reads out as the product name rather than the kana", () => {
        renderUI(<Wordmark />);
        const mark = screen.getByLabelText("monori");
        expect(mark).toHaveTextContent("ものり");
    });

    it("sets its own type size, defaulting to 23px", () => {
        renderUI(<Wordmark />);
        expect(screen.getByLabelText("monori")).toHaveStyle({ fontSize: "23px" });
    });

    // the shell and the landing page ask for different sizes off the same mark
    it("takes the size it is given", () => {
        const { unmount } = renderUI(<Wordmark size={20} />);
        expect(screen.getByLabelText("monori")).toHaveStyle({ fontSize: "20px" });
        unmount();

        renderUI(<Wordmark size={22} />);
        expect(screen.getByLabelText("monori")).toHaveStyle({ fontSize: "22px" });
    });

    // only the trailing り is tinted, so it has to be its own element
    it("splits the trailing kana out so it can be styled apart", () => {
        renderUI(<Wordmark />);
        const mark = screen.getByLabelText("monori");
        const tail = mark.querySelector<HTMLElement>(".wordmark__tail")!;
        expect(tail).toHaveTextContent("り");
        expect(mark.firstChild!.textContent).toBe("もの");
    });
});
