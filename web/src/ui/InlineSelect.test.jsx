import { describe, expect, it, vi } from "vitest";
import { renderUI, screen } from "../test/render.jsx";
import InlineSelect from "./InlineSelect.jsx";

describe("InlineSelect", () => {
    it("filters grouped options by group name or option label and submits the chosen value", async () => {
        const onChange = vi.fn();
        const { user } = renderUI(
            <InlineSelect
                searchable
                value="rent"
                onChange={onChange}
                data={[
                    { value: "none", label: "Uncategorized" },
                    {
                        group: "Home",
                        kind: "expense",
                        options: [
                            { value: "rent", label: "Rent" },
                            { value: "power", label: "Electricity" },
                        ],
                    },
                    {
                        group: "Income",
                        kind: "income",
                        options: [{ value: "pay", label: "Salary" }],
                    },
                ]}
            />,
        );

        await user.click(screen.getByRole("button", { name: "Rent" }));
        expect(screen.getByRole("option", { name: "Rent" })).toHaveAttribute(
            "data-selected",
            "true",
        );
        expect(screen.getByRole("option", { name: "Electricity" })).not.toHaveAttribute(
            "data-selected",
        );
        const search = screen.getByRole("textbox");
        await user.type(search, "home");
        expect(screen.getByRole("option", { name: "Rent" })).toBeInTheDocument();
        expect(screen.getByRole("option", { name: "Electricity" })).toBeInTheDocument();
        expect(screen.queryByRole("option", { name: "Salary" })).not.toBeInTheDocument();

        await user.clear(search);
        await user.type(search, "elec");
        await user.click(screen.getByRole("option", { name: "Electricity" }));
        expect(onChange).toHaveBeenCalledWith("power");
    });

    it("shows an empty result for a search that matches neither group nor option", async () => {
        const { user } = renderUI(
            <InlineSelect
                searchable
                value={null}
                onChange={() => {}}
                data={["January", "February"]}
            />,
        );
        await user.click(screen.getByRole("button", { name: "—" }));
        await user.type(screen.getByRole("textbox"), "zzz");
        expect(screen.getByText("Nothing found")).toBeInTheDocument();
    });
});
