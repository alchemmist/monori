import { describe, expect, it, vi } from "vitest";
import BudgetCell from "./BudgetCell.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("BudgetCell", () => {
    it("shows the amount in rubles as a button", () => {
        renderUI(<BudgetCell value={123456} onChange={() => {}} />);
        const cell = screen.getByRole("button");
        expect(cell).toHaveTextContent("1 235");
        expect(cell).toHaveAttribute("tabindex", "0");
    });

    it("takes a custom tabIndex", () => {
        renderUI(<BudgetCell value={0} onChange={() => {}} tabIndex={-1} />);
        expect(screen.getByRole("button")).toHaveAttribute("tabindex", "-1");
    });

    it("opens an input seeded with the value in rubles on click", async () => {
        const { user } = renderUI(<BudgetCell value={500000} onChange={() => {}} />);
        await user.click(screen.getByRole("button"));
        const input = screen.getByRole("textbox");
        expect(input).toHaveValue("5000");
        expect(input).toHaveFocus();
    });

    it("opens with an empty draft when the value is zero", async () => {
        const { user } = renderUI(<BudgetCell value={0} onChange={() => {}} />);
        await user.click(screen.getByRole("button"));
        expect(screen.getByRole("textbox")).toHaveValue("");
    });

    it.each(["{Enter}", " "])("opens on keyboard %s", async (key) => {
        const { user } = renderUI(<BudgetCell value={100} onChange={() => {}} />);
        screen.getByRole("button").focus();
        await user.keyboard(key);
        expect(screen.getByRole("textbox")).toBeInTheDocument();
    });

    it("ignores other keys", async () => {
        const { user } = renderUI(<BudgetCell value={100} onChange={() => {}} />);
        screen.getByRole("button").focus();
        await user.keyboard("x");
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    });

    it("commits the typed amount as kopecks on Enter", async () => {
        const onChange = vi.fn();
        const { user } = renderUI(<BudgetCell value={0} onChange={onChange} />);
        await user.click(screen.getByRole("button"));
        await user.type(screen.getByRole("textbox"), "1234,50{Enter}");
        expect(onChange).toHaveBeenCalledWith(123450);
        expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("commits on Tab and on blur", async () => {
        const onChange = vi.fn();
        const { user } = renderUI(<BudgetCell value={0} onChange={onChange} />);
        await user.click(screen.getByRole("button"));
        await user.keyboard("70{Tab}");
        expect(onChange).toHaveBeenCalledWith(7000);
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    });

    it("discards the draft on Escape", async () => {
        const onChange = vi.fn();
        const { user } = renderUI(<BudgetCell value={20000} onChange={onChange} />);
        await user.click(screen.getByRole("button"));
        await user.keyboard("999{Escape}");
        expect(onChange).not.toHaveBeenCalled();
        expect(screen.getByRole("button")).toHaveTextContent("200");
    });

    it("does not fire when the amount is unchanged", async () => {
        const onChange = vi.fn();
        const { user } = renderUI(<BudgetCell value={30000} onChange={onChange} />);
        await user.click(screen.getByRole("button"));
        await user.keyboard("{Enter}");
        expect(onChange).not.toHaveBeenCalled();
    });

    it("does not fire when the draft is not a number", async () => {
        const onChange = vi.fn();
        const { user } = renderUI(<BudgetCell value={0} onChange={onChange} />);
        await user.click(screen.getByRole("button"));
        await user.clear(screen.getByRole("textbox"));
        await user.type(screen.getByRole("textbox"), "abc{Enter}");
        expect(onChange).not.toHaveBeenCalled();
    });

    it("clears the amount when the field is emptied", async () => {
        const onChange = vi.fn();
        const { user } = renderUI(<BudgetCell value={5000} onChange={onChange} />);
        await user.click(screen.getByRole("button"));
        await user.clear(screen.getByRole("textbox"));
        await user.keyboard("{Enter}");
        expect(onChange).toHaveBeenCalledWith(0);
    });
});
