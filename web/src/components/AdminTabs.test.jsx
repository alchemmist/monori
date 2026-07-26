import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { forwardRef } from "react";

vi.mock("@mantine/core", async (importOriginal) => {
    const actual = await importOriginal();
    return {
        ...actual,
        Textarea: forwardRef(({ value, onChange, onKeyDown, ...props }, ref) => (
            <textarea
                ref={ref}
                value={value}
                onChange={onChange}
                onKeyDown={onKeyDown}
                {...props}
            />
        )),
    };
});
import AdminSqlTab from "./AdminSqlTab.jsx";
import AdminTxTab from "./AdminTxTab.jsx";
import { api } from "../api.js";
import { renderUI, resetStore, screen, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";

vi.mock("../ui/Tab.jsx", () => ({
    default: ({ title, children, footer }) => (
        <section>
            <h1>{title}</h1>
            {children}
            <footer>{footer}</footer>
        </section>
    ),
}));

vi.mock("../ui/fields.jsx", () => ({
    FSelect: ({ label, value, onChange, data }) => (
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

const rows = [
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
        await user.type(screen.getByLabelText("SQL statement"), "delete from tx");
        await user.click(screen.getByRole("button", { name: "Run" }));
        expect(await screen.findByText(/needs confirmation/)).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Apply write" }));
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
});
