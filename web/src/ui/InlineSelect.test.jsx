import { describe, expect, it, vi } from "vitest";
import InlineSelect from "./InlineSelect.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("InlineSelect", () => {
    it("renders a button with the current value and placeholder text when empty", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["Red", "Green", "Blue"]}
                placeholder="Pick one"
            />,
        );
        const btn = screen.getByRole("button");
        expect(btn).toHaveTextContent("Pick one");
        expect(btn).toHaveClass("gsel");
    });

    it("shows the current selection instead of placeholder", () => {
        renderUI(
            <InlineSelect
                value="red"
                onChange={() => {}}
                data={[{ value: "red", label: "Red" }]}
                placeholder="Pick one"
            />,
        );
        expect(screen.getByRole("button")).toHaveTextContent("Red");
    });

    it("normalizes string data to {value, label} shape", () => {
        renderUI(
            <InlineSelect
                value="apple"
                onChange={() => {}}
                data={["apple", "banana"]}
            />,
        );
        expect(screen.getByRole("button")).toHaveTextContent("apple");
    });

    it("renders a label inside the button when field=true", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
                label="Category"
                field
            />,
        );
        expect(screen.getByText("Category")).toHaveClass("gsel__label");
    });

    it("adds the small class for small=true", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
                small
            />,
        );
        expect(screen.getByRole("button")).toHaveClass("gsel_s");
    });

    it("adds the borderless class when borderless=true", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
                borderless
            />,
        );
        expect(screen.getByRole("button")).toHaveClass("gsel_borderless");
    });

    it("adds the field class when field=true", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
                field
            />,
        );
        expect(screen.getByRole("button")).toHaveClass("gsel_field");
    });

    it("merges custom className", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
                className="my-class"
            />,
        );
        expect(screen.getByRole("button")).toHaveClass("gsel", "my-class");
    });

    it("applies custom style to the button", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
                style={{ width: "200px" }}
            />,
        );
        expect(screen.getByRole("button")).toHaveStyle("width: 200px");
    });

    it("responds to click events", async () => {
        const { user } = renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["Apple", "Banana"]}
            />,
        );
        const btn = screen.getByRole("button");
        await user.click(btn);
        expect(btn).toHaveAttribute("aria-haspopup", "listbox");
    });

    it("handles data as object shape with {value, label}", () => {
        renderUI(
            <InlineSelect
                value="blue"
                onChange={() => {}}
                data={[
                    { value: "red", label: "Red color" },
                    { value: "blue", label: "Blue color" },
                ]}
            />,
        );
        expect(screen.getByRole("button")).toHaveTextContent("Blue color");
    });

    it("accepts data with group objects", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={[
                    {
                        group: "Fruits",
                        kind: "fruit",
                        options: ["Apple", "Banana"],
                    },
                    {
                        group: "Veggies",
                        kind: "veggie",
                        options: ["Carrot", "Lettuce"],
                    },
                ]}
            />,
        );
        expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("accepts mixed loose options and section objects", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={[
                    { value: "other", label: "Other" },
                    {
                        group: "Common",
                        options: ["Red", "Blue"],
                    },
                ]}
            />,
        );
        expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("supports searchable mode", async () => {
        const { user } = renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["Apple", "Banana"]}
                searchable
            />,
        );
        await user.click(screen.getByRole("button"));
        expect(await screen.findByPlaceholderText("Search")).toBeInTheDocument();
    });

    it("uses placeholder — by default", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
            />,
        );
        expect(screen.getByRole("button")).toHaveTextContent("—");
    });

    it("uses custom placeholder text", () => {
        renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
                placeholder="Choose"
            />,
        );
        expect(screen.getByRole("button")).toHaveTextContent("Choose");
    });

    it("renders with current value properly set", () => {
        renderUI(
            <InlineSelect
                value="banana"
                onChange={() => {}}
                data={["apple", "banana"]}
            />,
        );
        expect(screen.getByRole("button")).toHaveTextContent("banana");
    });

    it("renders chevron icon in button", () => {
        const { container } = renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
            />,
        );
        expect(container.querySelector(".gsel__chev")).toBeInTheDocument();
    });

    it("renders empty state without current value", () => {
        const { container } = renderUI(
            <InlineSelect
                value={null}
                onChange={() => {}}
                data={["a"]}
            />,
        );
        expect(container.querySelector(".gsel__text_empty")).toBeInTheDocument();
    });

    it("renders non-empty state with current value", () => {
        const { container } = renderUI(
            <InlineSelect
                value="apple"
                onChange={() => {}}
                data={["apple"]}
            />,
        );
        expect(container.querySelector(".gsel__text_empty")).not.toBeInTheDocument();
    });
});
