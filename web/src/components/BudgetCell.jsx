import { useEffect, useRef, useState } from "react";
import { rub, parseRub } from "../format.js";

/**
 * Inline-editable budget amount. Click (or focus+Enter) to edit; Enter saves,
 * Escape cancels. Recalculation happens in the same frame via the store.
 */
export default function BudgetCell({ value, onChange, tabIndex = 0 }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const start = () => {
    setDraft(value ? String(value / 100) : "");
    setEditing(true);
  };

  const commit = () => {
    const kop = parseRub(draft);
    setEditing(false);
    if (kop !== null && kop !== value) onChange(kop);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="budget-cell__input"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") setEditing(false);
          if (e.key === "Tab") commit();
        }}
      />
    );
  }

  return (
    <span
      className="budget-cell money num"
      role="button"
      tabIndex={tabIndex}
      onClick={start}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          start();
        }
      }}
      style={{ color: value ? "var(--m-text)" : "var(--m-text-faint)" }}
    >
      {rub(value)}
    </span>
  );
}
