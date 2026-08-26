import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { forwardRef } from "react";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import type { AdminTransaction } from "../types.js";

type MockTextareaProps = ComponentPropsWithoutRef<"textarea"> & {
    autosize?: boolean;
    minRows?: number;
    maxRows?: number;
};

vi.mock("@mantine/core", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@mantine/core")>();
    return {
        ...actual,
        Textarea: forwardRef<HTMLTextAreaElement, MockTextareaProps>(
            ({ value, onChange, onKeyDown, ...props }, ref) => {
                delete props.autosize;
                delete props.minRows;
                delete props.maxRows;
                return (
                    <textarea
                        ref={ref}
                        value={value}
                        onChange={onChange}
                        onKeyDown={onKeyDown}
                        {...props}
                    />
                );
            },
        ),
    };
});
import AdminSqlTab, { isPendingWrite } from "./AdminSqlTab.jsx";
import AdminTxTab from "./AdminTxTab.jsx";
import { api } from "../api.js";
import { fireEvent, renderUI, resetStore, screen, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";

vi.mock("../ui/Tab.jsx", () => ({
    default: ({
        title,
        children,
        footer,
    }: {
        title: ReactNode;
        children?: ReactNode;
        footer?: ReactNode;
    }) => (
        <section>
            <h1>{title}</h1>
            {children}
            <footer>{footer}</footer>
        </section>
    ),
}));

vi.mock("../ui/fields.jsx", () => ({
    FSelect: ({
        label,
        value,
        onChange,
        data,
    }: {
        label: ReactNode;
        value: string;
        onChange: (value: string) => void;
        data: Array<{ value: string; label: string }>;
    }) => (
        <label>
            {label}
            <select value={value} onChange={(e) => onChange(e.target.value)}>
                {data.map((option) => (
                    <option key={option.value} value={option.value}>
                        {option.label}
                    </option>
                ))}
            </select>
        </label>
    ),
}));

const rows: AdminTransaction[] = [
    {
        id: 1,
        account: "Card",
        date: "2026-01-01",
        description: "Coffee",
        category: "Food",
        amount: -350,
    },
    {
        id: 2,
        account: "Cash",
        date: "2026-01-02",
        description: "Salary",
        category: "Income",
        amount: 10000,
    },
];

describe("AdminSqlTab", () => {
    beforeEach(() => {
        resetStore();
    });
    afterEach(() => vi.restoreAllMocks());

    it("recognizes only non-empty pending writes", () => {
        expect(isPendingWrite(null)).toBe(false);
        expect(isPendingWrite("")).toBe(false);
        expect(isPendingWrite("delete from tx")).toBe(true);
    });

    it("runs a read query, renders values safely and restores it from history", async () => {
        vi.spyOn(api, "adminSql").mockResolvedValue({
            kind: "read",
            rowCount: 1,
            elapsedMs: 3,
            columns: ["name", "value"],
            rows: [["x".repeat(205), null]],
            truncated: true,
        });
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        await user.type(screen.getByLabelText("SQL statement"), "select 1");
        await user.click(screen.getByRole("button", { name: "Run" }));
        await screen.findByText(/1 row · 3 ms · showing first 1 rows/);
        expect(screen.getByText("NULL")).toBeInTheDocument();
        // long values are cut to exactly 200 characters plus the ellipsis
        expect(screen.getByText(/…$/)).toHaveTextContent(new RegExp(`^x{200}…$`));
        await user.click(screen.getByRole("button", { name: "select 1" }));
        expect(screen.getByLabelText("SQL statement")).toHaveValue("select 1");
    });

    it("turns a refused write into a confirmation and bumps admin data after apply", async () => {
        const run = vi
            .spyOn(api, "adminSql")
            .mockRejectedValueOnce(new Error("write needs confirmation: 2 rows"))
            .mockResolvedValueOnce({
                kind: "write",
                rowCount: 2,
                elapsedMs: 5,
                columns: [],
                rows: [],
            });
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
        await user.type(screen.getByLabelText("SQL statement"), "delete from tx");
        const runButton = screen.getByRole("button", { name: "Run" });
        expect(runButton).toBeEnabled();
        await user.click(runButton);
        expect(await screen.findByText(/needs confirmation/)).toBeInTheDocument();
        const apply = screen.getByRole("button", { name: "Apply write" });
        expect(apply).toHaveStyle("--button-color: var(--m-accent-contrast)");
        await user.click(apply);
        await waitFor(() => expect(run).toHaveBeenLastCalledWith("delete from tx", true, false));
        expect(useStore.getState().adminTick).toBe(1);
    });

    it("reports ordinary SQL errors", async () => {
        vi.spyOn(api, "adminSql").mockRejectedValue(new Error("syntax error"));
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        await user.type(screen.getByLabelText("SQL statement"), "bad sql");
        await user.click(screen.getByRole("button", { name: "Dry run" }));
        expect(await screen.findByText("syntax error")).toBeInTheDocument();
    });

    it("runs keyboard dry reads and explains whether a dry run would write", async () => {
        const run = vi
            .spyOn(api, "adminSql")
            .mockResolvedValueOnce({
                kind: "dry",
                wouldWrite: false,
                rowCount: 0,
                elapsedMs: 4,
                columns: ["id"],
                rows: [],
            })
            .mockResolvedValueOnce({
                kind: "dry",
                wouldWrite: true,
                rowCount: 2,
                elapsedMs: 6,
                columns: [],
                rows: [],
            });
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        const area = screen.getByLabelText("SQL statement");
        await user.type(area, "select * from tx");
        fireEvent.keyDown(area, { key: "Enter", ctrlKey: true, shiftKey: true });
        await screen.findByText("Rolled back — nothing was written. The query returned 0 rows.");
        expect(run).toHaveBeenLastCalledWith("select * from tx", false, true);
        expect(screen.getByText("No rows")).toBeInTheDocument();

        await user.clear(area);
        await user.type(area, "update tx set amount = 0");
        await user.click(screen.getByRole("button", { name: "Dry run" }));
        expect(
            await screen.findByText(
                "Rolled back — nothing was written. Applying this would affect 2 rows.",
            ),
        ).toBeInTheDocument();
        expect(run).toHaveBeenLastCalledWith("update tx set amount = 0", false, true);
    });

    it("cancels a pending write when the statement changes", async () => {
        vi.spyOn(api, "adminSql").mockRejectedValueOnce(
            new Error("write needs confirmation: 1 row"),
        );
        const { user } = renderUI(<AdminSqlTab onClose={vi.fn()} />);
        const area = screen.getByLabelText("SQL statement");
        await user.type(area, "delete from tx");
        await user.click(screen.getByRole("button", { name: "Run" }));
        expect(await screen.findByRole("button", { name: "Apply write" })).toBeInTheDocument();
        await user.type(area, " where id = 1");
        expect(screen.queryByRole("button", { name: "Apply write" })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Run" })).toBeInTheDocument();
    });
});

describe("AdminTxTab", () => {
    beforeEach(() => {
        resetStore();
        useStore.setState({ adminTick: 0 });
    });
    afterEach(() => vi.restoreAllMocks());

    it("loads, filters, selects and deletes the chosen transactions after confirmation", async () => {
        const load = vi
            .spyOn(api, "adminUserTransactions")
            .mockResolvedValueOnce(rows)
            .mockResolvedValueOnce(rows)
            .mockResolvedValueOnce(rows);
        const remove = vi
            .spyOn(api, "adminDeleteUserTransactions")
            .mockResolvedValue({ deleted: 1 });
        const { user } = renderUI(
            <AdminTxTab user={{ id: 7, email: "person@example.test" }} onClose={vi.fn()} />,
        );
        await screen.findByText("Coffee");
        await user.click(screen.getByText("Coffee"));
        expect(screen.getByText("1 selected")).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Delete selected" }));
        await user.click(screen.getByRole("button", { name: "Delete 1 — sure?" }));
        await waitFor(() => expect(remove).toHaveBeenCalledWith(7, [1]));
        expect(useStore.getState().adminTick).toBe(1);
        expect(load).toHaveBeenCalled();
    });

    it("shows an empty state after account filtering", async () => {
        vi.spyOn(api, "adminUserTransactions").mockResolvedValue(rows);
        const { user } = renderUI(
            <AdminTxTab user={{ id: 7, email: "person@example.test" }} onClose={vi.fn()} />,
        );
        await screen.findByText("Coffee");
        await user.selectOptions(screen.getByLabelText("Account"), "Cash");
        expect(screen.getByText("Salary")).toBeInTheDocument();
    });

    it("loads every page and selects only the rows visible under an account filter", async () => {
        const later = {
            id: 3,
            account: "Card",
            date: "2026-01-03",
            description: "Rent",
            category: "Home",
            amount: -500,
        };
        vi.spyOn(api, "adminUserTransactions")
            .mockResolvedValueOnce([...rows, later])
            .mockResolvedValueOnce([]);
        const { user } = renderUI(
            <AdminTxTab user={{ id: 7, email: "person@example.test" }} onClose={vi.fn()} />,
        );

        await screen.findByText("Rent");
        await user.selectOptions(screen.getByLabelText("Account"), "Card");
        await user.click(screen.getByLabelText("Select all visible (2)"));
        expect(screen.getByText("2 selected")).toBeInTheDocument();
        await user.selectOptions(screen.getByLabelText("Account"), "Cash");
        expect(screen.getByLabelText("Select all visible (1)")).not.toBeChecked();
        expect(screen.getByText("2 selected")).toBeInTheDocument();
    });

    it("requests a second page after a full page and renders its final transaction", async () => {
        const firstPage = Array.from({ length: 1000 }, (_, i) => ({
            id: i + 1,
            account: "Card",
            date: "2026-01-01",
            description: `Transaction ${i + 1}`,
            category: "Food",
            amount: -1,
        }));
        const finalRow = { ...rows[1]!, id: 1001, description: "Last page row" };
        const load = vi
            .spyOn(api, "adminUserTransactions")
            .mockResolvedValueOnce(firstPage)
            .mockResolvedValueOnce([finalRow]);
        renderUI(<AdminTxTab user={{ id: 7, email: "person@example.test" }} onClose={vi.fn()} />);
        expect(await screen.findByText("Last page row")).toBeInTheDocument();
        expect(load).toHaveBeenNthCalledWith(1, 7, { limit: 1000, offset: 0 });
        expect(load).toHaveBeenNthCalledWith(2, 7, { limit: 1000, offset: 1000 });
    });

    it("disarms deletion after a selection changes and reports a failed delete", async () => {
        vi.spyOn(api, "adminUserTransactions").mockResolvedValue(rows);
        const remove = vi
            .spyOn(api, "adminDeleteUserTransactions")
            .mockRejectedValue(new Error("permission denied"));
        const { user } = renderUI(
            <AdminTxTab user={{ id: 7, email: "person@example.test" }} onClose={vi.fn()} />,
        );
        await screen.findByText("Coffee");
        await user.click(screen.getByText("Coffee"));
        await user.click(screen.getByRole("button", { name: "Delete selected" }));
        expect(screen.getByRole("button", { name: "Delete 1 — sure?" })).toBeInTheDocument();
        await user.click(screen.getByText("Salary"));
        expect(screen.getByRole("button", { name: "Delete selected" })).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Delete selected" }));
        await user.click(screen.getByRole("button", { name: "Delete 2 — sure?" }));
        await waitFor(() => expect(remove).toHaveBeenCalledWith(7, [1, 2]));
        expect(await screen.findByText("Delete failed")).toBeInTheDocument();
        expect(screen.getByText("2 selected")).toBeInTheDocument();
    });
});
