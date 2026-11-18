import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

interface EditableCellProps {
    draft?: string | null;
    display?: ReactNode;
    onCommit: (value: string) => void;
    label: string;
    type?: React.HTMLInputTypeAttribute;
    align?: CSSProperties["textAlign"];
    placeholder?: ReactNode;
    width?: number | string;
}

/**
 * Click-to-edit table cell, the text/date sibling of BudgetCell: the row reads
 * as plain text until you click it, then turns into an input. Enter and Tab
 * save, Escape and an unchanged value leave the row alone.
 *
 * `draft` is what the input starts with (the raw value, not the formatted one)
 * and `onCommit` receives the raw string back — parsing belongs to the caller,
 * since a date, a description and an amount each mean something different.
 */
export default function EditableCell({
    draft,
    display,
    onCommit,
    label,
    type = "text",
    align = "left",
    placeholder = "—",
    width,
}: EditableCellProps) {
    const [editing, setEditing] = useState(false);
    const [value, setValue] = useState("");
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (editing) {
            inputRef.current?.focus();
            if (type === "text") inputRef.current?.select();
        }
    }, [editing, type]);

    const start = () => {
        setValue(draft ?? "");
        setEditing(true);
    };

    const commit = () => {
        setEditing(false);
        if (value !== (draft ?? "")) onCommit(value);
    };

    if (editing) {
        return (
            <input
                ref={inputRef}
                type={type}
                className="tx-edit__input"
                aria-label={label}
                style={{ textAlign: align, width }}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onBlur={commit}
                onKeyDown={(e) => {
                    // the ledger listens for keys too, so keep them in here
                    e.stopPropagation();
                    if (e.key === "Enter") commit();
                    if (e.key === "Escape") setEditing(false);
                }}
            />
        );
    }

    const empty = display === "" || display == null;
    return (
        <span
            className={`tx-edit${empty ? " tx-edit_empty" : ""}`}
            role="button"
            tabIndex={0}
            aria-label={label}
            style={{ textAlign: align, minWidth: width }}
            onClick={start}
            onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    start();
                }
            }}
        >
            {empty ? placeholder : display}
        </span>
    );
}
