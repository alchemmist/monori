import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderUI, screen } from "../test/render.jsx";
import EditableCell from "./EditableCell.jsx";

beforeEach(() => {
    vi.restoreAllMocks();
});

describe("EditableCell", () => {
    it("shows the display value as a button until clicked", () => {
        renderUI(<EditableCell draft="hi" display="Hello" label="cell" onCommit={vi.fn()} />);
        expect(screen.getByRole("button", { name: "cell" })).toHaveTextContent("Hello");
        expect(screen.queryByRole("textbox")).toBeNull();
    });

    it("shows the placeholder when the display is empty", () => {
        renderUI(
            <EditableCell draft="" display="" label="cell" placeholder="—" onCommit={vi.fn()} />,
        );
        expect(screen.getByRole("button", { name: "cell" })).toHaveTextContent("—");
    });

    it("treats a null display as empty", () => {
        renderUI(
            <EditableCell
                draft=""
                display={null}
                label="cell"
                placeholder="none"
                onCommit={vi.fn()}
            />,
        );
        expect(screen.getByRole("button", { name: "cell" })).toHaveTextContent("none");
    });

    it("enters edit mode on click and seeds the input from draft", async () => {
        const { user } = renderUI(
            <EditableCell draft="raw" display="Formatted" label="cell" onCommit={vi.fn()} />,
        );
        await user.click(screen.getByRole("button", { name: "cell" }));
        const input = screen.getByRole("textbox", { name: "cell" });
        expect(input).toHaveValue("raw");
    });

    it("commits the typed value on Enter", async () => {
        const onCommit = vi.fn();
        const { user } = renderUI(
            <EditableCell draft="" display="" label="cell" onCommit={onCommit} />,
        );
        await user.click(screen.getByRole("button", { name: "cell" }));
        await user.type(screen.getByRole("textbox", { name: "cell" }), "world{Enter}");
        expect(onCommit).toHaveBeenCalledWith("world");
        expect(screen.queryByRole("textbox")).toBeNull();
    });

    it("commits on blur", async () => {
        const onCommit = vi.fn();
        const { user } = renderUI(
            <EditableCell draft="a" display="a" label="cell" onCommit={onCommit} />,
        );
        await user.click(screen.getByRole("button", { name: "cell" }));
        const input = screen.getByRole("textbox", { name: "cell" });
        await user.clear(input);
        await user.type(input, "b");
        await user.tab();
        expect(onCommit).toHaveBeenCalledWith("b");
    });

    it("does not commit when the value is unchanged", async () => {
        const onCommit = vi.fn();
        const { user } = renderUI(
            <EditableCell draft="same" display="same" label="cell" onCommit={onCommit} />,
        );
        await user.click(screen.getByRole("button", { name: "cell" }));
        await user.type(screen.getByRole("textbox", { name: "cell" }), "{Enter}");
        expect(onCommit).not.toHaveBeenCalled();
    });

    it("cancels on Escape without committing", async () => {
        const onCommit = vi.fn();
        const { user } = renderUI(
            <EditableCell draft="orig" display="orig" label="cell" onCommit={onCommit} />,
        );
        await user.click(screen.getByRole("button", { name: "cell" }));
        const input = screen.getByRole("textbox", { name: "cell" });
        await user.clear(input);
        await user.type(input, "changed{Escape}");
        expect(onCommit).not.toHaveBeenCalled();
        expect(screen.queryByRole("textbox")).toBeNull();
    });

    it("opens edit mode from the keyboard with Enter", async () => {
        const { user } = renderUI(
            <EditableCell draft="x" display="x" label="cell" onCommit={vi.fn()} />,
        );
        const button = screen.getByRole("button", { name: "cell" });
        button.focus();
        await user.keyboard("{Enter}");
        expect(screen.getByRole("textbox", { name: "cell" })).toBeInTheDocument();
    });

    it("opens edit mode from the keyboard with Space", async () => {
        const { user } = renderUI(
            <EditableCell draft="x" display="x" label="cell" onCommit={vi.fn()} />,
        );
        const button = screen.getByRole("button", { name: "cell" });
        button.focus();
        await user.keyboard("{ }");
        expect(screen.getByRole("textbox", { name: "cell" })).toBeInTheDocument();
    });

    it("renders a date input and does not auto-select its text", async () => {
        const { user } = renderUI(
            <EditableCell
                draft="2026-03-05"
                display="05.03.2026"
                label="date"
                type="date"
                onCommit={vi.fn()}
            />,
        );
        await user.click(screen.getByRole("button", { name: "date" }));
        const input = screen.getByLabelText("date");
        expect(input).toHaveAttribute("type", "date");
        expect(input).toHaveValue("2026-03-05");
    });
});
