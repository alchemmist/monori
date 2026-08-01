import { useLayoutEffect, useRef } from "react";
import type { ChangeEvent } from "react";
import { groupAmount } from "../format.js";

/** Everything that is not a group separator — the caret is tracked in these,
 * since the separators come and go under it while the digits are typed. */
const SIGNIFICANT = /[\d.,-]/;

/** Amount field behaviour shared by every place money is typed: the digits are
 * grouped as they are typed, and the caret is put back where the person left
 * it rather than being thrown to the end of the field. */
export default function useAmountField(setValue: (value: string) => void) {
    const ref = useRef<HTMLInputElement>(null);
    const caret = useRef<number | null>(null);

    useLayoutEffect(() => {
        const node = ref.current;
        if (!node || caret.current == null) return;
        const want = caret.current;
        caret.current = null;
        let i = 0;
        let seen = 0;
        while (i < node.value.length && seen < want) {
            if (SIGNIFICANT.test(node.value[i]!)) seen += 1;
            i += 1;
        }
        node.setSelectionRange(i, i);
    });

    const onChange = (e: ChangeEvent<HTMLInputElement>) => {
        const el = e.target;
        const head = el.value.slice(0, el.selectionStart ?? el.value.length);
        caret.current = Array.from(head).filter((c) => SIGNIFICANT.test(c)).length;
        setValue(groupAmount(el.value));
    };

    return { ref, onChange, inputMode: "decimal" as const };
}
