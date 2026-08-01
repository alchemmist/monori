import { useState } from "react";
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import useAmountField from "./useAmountField.js";

const NB = " ";

/** A minimal controlled money input wired to the hook, exactly as the real
 * fields use it: the ref for caret work, onChange for grouping. */
function Field({ initial = "", onValue }: { initial?: string; onValue?: (value: string) => void }) {
    const [v, setV] = useState(initial);
    const set = (next: string) => {
        setV(next);
        onValue?.(next);
    };
    const { ref, onChange, inputMode } = useAmountField(set);
    return (
        <input ref={ref} value={v} inputMode={inputMode} onChange={onChange} data-testid="amt" />
    );
}

/** jsdom keeps a real value + selection on the node; drive the change the way
 * the browser would, with the caret sitting where the person left it. */
const edit = (input: HTMLInputElement, value: string, caret = value.length) => {
    fireEvent.change(input, { target: { value, selectionStart: caret, selectionEnd: caret } });
};

describe("useAmountField", () => {
    it("marks the field as a decimal keypad", () => {
        const { getByTestId } = render(<Field />);
        expect((getByTestId("amt") as HTMLInputElement).inputMode).toBe("decimal");
    });

    it("groups the digits as they are typed", () => {
        const onValue = vi.fn();
        const { getByTestId } = render(<Field onValue={onValue} />);
        edit(getByTestId("amt") as HTMLInputElement, "1234567");
        // grouped with non-breaking spaces, never plain spaces
        expect(onValue).toHaveBeenCalledWith(`1${NB}234${NB}567`);
    });

    it("keeps a negative sign and a decimal separator", () => {
        const onValue = vi.fn();
        const { getByTestId } = render(<Field onValue={onValue} />);
        edit(getByTestId("amt") as HTMLInputElement, "-1234,5");
        expect(onValue).toHaveBeenCalledWith(`-1${NB}234,5`);
    });

    it("puts the caret back by significant characters, not raw offset", () => {
        // caret sits after "123"; once "1234567" becomes "1 234 567" the three
        // significant chars land it after "1 23", at raw index 4 — not 3, and
        // not thrown to the end
        const input = render(<Field />).getByTestId("amt") as HTMLInputElement;
        edit(input, "1234567", 3);
        expect(input.value).toBe(`1${NB}234${NB}567`);
        expect(input.selectionStart).toBe(4);
    });

    it("counts significant characters, so the caret does not drift to the end", () => {
        // caret after the first four digits of a seven-digit amount stays on its
        // own group boundary rather than snapping to the tail
        const input = render(<Field />).getByTestId("amt") as HTMLInputElement;
        edit(input, "1234567", 4);
        expect(input.value).toBe(`1${NB}234${NB}567`);
        // four significant chars: after "1 234", raw index 5
        expect(input.selectionStart).toBe(5);
    });
});
