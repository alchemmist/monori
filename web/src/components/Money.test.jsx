import { describe, expect, it } from "vitest";
import { renderUI, screen } from "../test/render.jsx";
import { BalancePill, Money } from "./Money.jsx";

describe("Money", () => {
    it("formats the amount and dims a zero by default", () => {
        renderUI(<Money value={0} />);
        expect(screen.getByText("0")).toHaveClass("money_zero");
    });

    it("colours positive and negative amounts when asked", () => {
        const { rerender } = renderUI(<Money value={12500} signColor />);
        expect(screen.getByText("125")).toHaveClass("money_pos");
        rerender(<Money value={-12500} signColor />);
        expect(screen.getByText("-125")).toHaveClass("money_neg");
    });

    it.each([99, -99])("treats sub-ruble amount %s as zero", (value) => {
        renderUI(<Money value={value} signColor />);
        expect(screen.getByText("0")).toHaveClass("money_zero");
    });
});

describe("BalancePill", () => {
    it.each([
        [100, "balance-pill_pos"],
        [-100, "balance-pill_neg"],
        [0, "balance-pill_zero"],
        [99, "balance-pill_zero"],
        [-99, "balance-pill_zero"],
    ])("uses the balance tone for %s", (value, cls) => {
        renderUI(<BalancePill value={value} />);
        expect(document.querySelector(".balance-pill")).toHaveClass(cls);
    });
});
