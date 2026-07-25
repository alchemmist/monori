import { describe, expect, it, vi } from "vitest";
import { FTextInput, FTextArea, FSelect } from "./fields.jsx";
import { renderUI, screen } from "../test/render.jsx";

describe("FTextInput", () => {
    it("renders a text input with the gravity style", () => {
        renderUI(<FTextInput label="Name" />);
        const input = screen.getByRole("textbox");
        expect(input).toHaveClass("mi-input__field");
    });

    it("renders the label with the field style", () => {
        renderUI(<FTextInput label="Email" />);
        const label = screen.getByText("Email");
        expect(label).toHaveClass("mi-input__label");
    });

    it("forwards all props to the underlying TextInput", () => {
        renderUI(<FTextInput placeholder="Enter text" data-testid="input" />);
        const input = screen.getByTestId("input");
        expect(input).toHaveAttribute("placeholder", "Enter text");
    });

    it("applies custom classNames to the root wrapper", () => {
        const { container } = renderUI(
            <FTextInput label="Test" classNames={{ root: "custom-root" }} />,
        );
        expect(container.querySelector(".custom-root")).toBeInTheDocument();
    });

    it("handles value and onChange", async () => {
        const handleChange = vi.fn();
        const { user } = renderUI(
            <FTextInput value="hello" onChange={handleChange} />,
        );
        const input = screen.getByDisplayValue("hello");
        await user.clear(input);
        await user.type(input, "world");
        expect(handleChange).toHaveBeenCalled();
    });

    it("can be disabled", () => {
        renderUI(<FTextInput disabled />);
        expect(screen.getByRole("textbox")).toBeDisabled();
    });

    it("shows error state when error prop is passed", () => {
        renderUI(<FTextInput error="This is required" />);
        expect(screen.getByText("This is required")).toBeInTheDocument();
    });
});

describe("FTextArea", () => {
    it("renders a textarea with the gravity style", () => {
        renderUI(<FTextArea label="Comments" />);
        const textarea = screen.getByRole("textbox");
        expect(textarea.tagName).toBe("TEXTAREA");
        expect(textarea).toHaveClass("mi-input__field");
    });

    it("renders the label with the field style", () => {
        renderUI(<FTextArea label="Message" />);
        const label = screen.getByText("Message");
        expect(label).toHaveClass("mi-input__label");
    });

    it("forwards all props to the underlying Textarea", () => {
        renderUI(
            <FTextArea placeholder="Enter message" data-testid="textarea" />,
        );
        const textarea = screen.getByTestId("textarea");
        expect(textarea).toHaveAttribute("placeholder", "Enter message");
    });

    it("handles value and onChange", async () => {
        const handleChange = vi.fn();
        const { user } = renderUI(
            <FTextArea value="initial" onChange={handleChange} />,
        );
        const textarea = screen.getByDisplayValue("initial");
        await user.clear(textarea);
        await user.type(textarea, "updated");
        expect(handleChange).toHaveBeenCalled();
    });

    it("can be disabled", () => {
        renderUI(<FTextArea disabled />);
        expect(screen.getByRole("textbox")).toBeDisabled();
    });

    it("shows error state when error prop is passed", () => {
        renderUI(<FTextArea error="Validation failed" />);
        expect(screen.getByText("Validation failed")).toBeInTheDocument();
    });
});

describe("FSelect", () => {
    it("renders an InlineSelect with field=true", () => {
        renderUI(
            <FSelect
                value={null}
                onChange={() => {}}
                data={["Apple", "Banana"]}
            />,
        );
        const btn = screen.getByRole("button");
        expect(btn).toHaveClass("gsel_field");
    });

    it("passes through label and other props", () => {
        renderUI(
            <FSelect
                label="Category"
                value={null}
                onChange={() => {}}
                data={["A", "B"]}
            />,
        );
        expect(screen.getByText("Category")).toHaveClass("gsel__label");
    });

    it("defaults to placeholder — if not provided", () => {
        renderUI(
            <FSelect
                value={null}
                onChange={() => {}}
                data={["A", "B"]}
            />,
        );
        expect(screen.getByRole("button")).toHaveTextContent("—");
    });

    it("allows custom placeholder", () => {
        renderUI(
            <FSelect
                placeholder="Choose one"
                value={null}
                onChange={() => {}}
                data={["A", "B"]}
            />,
        );
        expect(screen.getByRole("button")).toHaveTextContent("Choose one");
    });

    it("shows the selected value", () => {
        renderUI(
            <FSelect
                value="apple"
                onChange={() => {}}
                data={[{ value: "apple", label: "Apple" }]}
            />,
        );
        expect(screen.getByRole("button")).toHaveTextContent("Apple");
    });

    it("forwards onChange to InlineSelect", () => {
        const onChange = vi.fn();
        renderUI(
            <FSelect
                value={null}
                onChange={onChange}
                data={["Red", "Blue"]}
            />,
        );
        expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("forwards all props to InlineSelect", async () => {
        const { user } = renderUI(
            <FSelect
                value={null}
                onChange={() => {}}
                data={["A", "B"]}
                searchable
            />,
        );
        await user.click(screen.getByRole("button"));
        expect(screen.getByPlaceholderText("Search")).toBeInTheDocument();
    });

    it("passes grouped data through to InlineSelect", () => {
        renderUI(
            <FSelect
                value={null}
                onChange={() => {}}
                data={[
                    {
                        group: "Warm",
                        options: ["Red", "Orange"],
                    },
                    {
                        group: "Cool",
                        options: ["Blue", "Purple"],
                    },
                ]}
            />,
        );
        const btn = screen.getByRole("button");
        expect(btn).toHaveClass("gsel_field");
    });
});
