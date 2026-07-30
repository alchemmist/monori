import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Checkbox } from "@mantine/core";
import { Plus, TrashBin } from "@gravity-ui/icons";
import { api } from "../api.js";
import { amountInput, money, parseRub } from "../format.js";
import { isDemo, useStore } from "../store.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FAmountInput, FSelect, FTextInput } from "../ui/fields.jsx";
import Tag from "../ui/Tag.jsx";
import "./recurring.css";

const today = () => new Date().toISOString().slice(0, 10);
const FREQUENCIES = ["daily", "weekly", "monthly", "yearly"].map((value) => ({
    value,
    label: value[0].toUpperCase() + value.slice(1),
}));

export default function RecurringPage() {
    const { snapshot, load, notify } = useStore();
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(!isDemo());
    const [dialog, setDialog] = useState(false);

    const refresh = useCallback(async () => {
        if (isDemo()) return;
        setLoading(true);
        try {
            const result = await api.recurring();
            setRows(result.rows);
            if (result.createdTransactionIds.length) {
                await load();
                notify({
                    title: `${result.createdTransactionIds.length} recurring transaction${result.createdTransactionIds.length === 1 ? "" : "s"} created`,
                    theme: "success",
                });
            }
            if (result.dueReminderIds?.length) {
                notify({
                    title: `${result.dueReminderIds.length} recurring transaction${result.dueReminderIds.length === 1 ? " is" : "s are"} due`,
                    theme: "info",
                });
            }
        } catch (error) {
            notify({ title: "Failed to load schedules", content: String(error), theme: "danger" });
        } finally {
            setLoading(false);
        }
    }, [load, notify]);

    useEffect(() => {
        refresh();
    }, [refresh]); // materialize due schedules once when the page opens

    const remove = async (id) => {
        try {
            await api.deleteRecurring(id);
            setRows((current) => current.filter((row) => row.id !== id));
        } catch (error) {
            notify({ title: "Failed to delete schedule", content: String(error), theme: "danger" });
        }
    };

    const accounts = new Map(snapshot.accounts.map((account) => [account.id, account.name]));
    const categories = new Map(snapshot.categories.map((category) => [category.id, category.name]));

    return (
        <div className="fade-in">
            <div className="budget-toolbar recurring-toolbar">
                <div>
                    <h1 className="page-title">Recurring transactions</h1>
                    <p className="recurring-subtitle">
                        Create transactions automatically on a schedule.
                    </p>
                </div>
                <Button
                    leftSection={<Plus width={16} height={16} />}
                    onClick={() => setDialog(true)}
                    disabled={isDemo()}
                >
                    Add schedule
                </Button>
            </div>
            {isDemo() && (
                <div className="card recurring-empty">Schedules are unavailable in demo mode.</div>
            )}
            {!isDemo() && !loading && rows.length === 0 && (
                <div className="card recurring-empty">No recurring transactions yet.</div>
            )}
            {!isDemo() && rows.length > 0 && (
                <div className="card recurring-list">
                    {rows.map((row) => (
                        <div className="recurring-row" key={row.id}>
                            <div className="recurring-row__main">
                                <strong>{row.payee || "Recurring transaction"}</strong>
                                <span>
                                    {accounts.get(row.accountId)} ·{" "}
                                    {categories.get(row.categoryId) ?? "Uncategorized"}
                                </span>
                            </div>
                            <div className="recurring-row__schedule">
                                <span>
                                    {row.interval === 1
                                        ? row.frequency
                                        : `Every ${row.interval} ${row.frequency}`}
                                </span>
                                <small>{row.active ? `Next: ${row.nextDate}` : "Completed"}</small>
                            </div>
                            <Tag theme={row.autoCreate ? "success" : "info"}>
                                {row.autoCreate ? "automatic" : "reminder"}
                            </Tag>
                            <span
                                className={`recurring-row__amount num ${row.amount < 0 ? "expense" : "income"}`}
                            >
                                {money(row.amount)}
                            </span>
                            <button
                                className="recurring-row__delete"
                                type="button"
                                aria-label={`Delete ${row.payee || "schedule"}`}
                                onClick={() => remove(row.id)}
                            >
                                <TrashBin width={16} height={16} />
                            </button>
                        </div>
                    ))}
                </div>
            )}
            {dialog && (
                <CreateScheduleDialog
                    snapshot={snapshot}
                    onClose={() => setDialog(false)}
                    onCreated={async () => {
                        setDialog(false);
                        await refresh();
                    }}
                    notify={notify}
                />
            )}
        </div>
    );
}

function CreateScheduleDialog({ snapshot, onClose, onCreated, notify }) {
    const [payee, setPayee] = useState("");
    const [description, setDescription] = useState("");
    const [amount, setAmount] = useState(amountInput(-1000));
    const [accountId, setAccountId] = useState(
        String(snapshot.accounts.find((a) => !a.archived)?.id ?? ""),
    );
    const [categoryId, setCategoryId] = useState("");
    const [frequency, setFrequency] = useState("monthly");
    const [interval, setInterval] = useState("1");
    const [startDate, setStartDate] = useState(today());
    const [endDate, setEndDate] = useState("");
    const [autoCreate, setAutoCreate] = useState(true);
    const [busy, setBusy] = useState(false);
    const parsedAmount = parseRub(amount);
    const incomeGroups = useMemo(
        () => new Set(snapshot.groups.filter((g) => g.kind === "income").map((g) => g.id)),
        [snapshot.groups],
    );
    const categoryOptions = useMemo(
        () =>
            snapshot.categories
                .filter(
                    (category) =>
                        !category.archived &&
                        (parsedAmount >= 0
                            ? incomeGroups.has(category.groupId)
                            : !incomeGroups.has(category.groupId)),
                )
                .map((category) => ({ value: String(category.id), label: category.name })),
        [incomeGroups, parsedAmount, snapshot.categories],
    );

    useEffect(() => {
        if (!categoryOptions.some((option) => option.value === categoryId))
            setCategoryId(categoryOptions[0]?.value ?? "");
    }, [categoryId, categoryOptions]);

    const save = async () => {
        if (parsedAmount == null || parsedAmount === 0) return;
        setBusy(true);
        try {
            await api.createRecurring({
                accountId: Number(accountId),
                categoryId: categoryId ? Number(categoryId) : null,
                payee: payee.trim(),
                description: description.trim(),
                amount: parsedAmount,
                frequency,
                interval: Number(interval),
                startDate,
                endDate: endDate || null,
                autoCreate,
            });
            await onCreated();
        } catch (error) {
            notify({ title: "Failed to create schedule", content: String(error), theme: "danger" });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title="New recurring transaction"
            onClose={onClose}
            applyText="Create schedule"
            onApply={save}
            applyLoading={busy}
            applyDisabled={!accountId || !startDate || parsedAmount == null || parsedAmount === 0}
        >
            <div className="recurring-form">
                <FTextInput
                    label="Payee"
                    value={payee}
                    onChange={(event) => setPayee(event.target.value)}
                    autoFocus
                />
                <FTextInput
                    label="Description (optional)"
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                />
                <FAmountInput label="Amount" value={amount} onChange={setAmount} />
                <FSelect
                    label="Account"
                    value={accountId}
                    onChange={setAccountId}
                    data={snapshot.accounts
                        .filter((a) => !a.archived)
                        .map((a) => ({ value: String(a.id), label: a.name }))}
                />
                <FSelect
                    label="Category"
                    value={categoryId}
                    onChange={setCategoryId}
                    data={categoryOptions}
                    clearable
                />
                <div className="recurring-form__pair">
                    <FSelect
                        label="Frequency"
                        value={frequency}
                        onChange={setFrequency}
                        data={FREQUENCIES}
                    />
                    <FTextInput
                        label="Every"
                        type="number"
                        min="1"
                        max="366"
                        value={interval}
                        onChange={(event) => setInterval(event.target.value)}
                    />
                </div>
                <div className="recurring-form__pair">
                    <FTextInput
                        label="Starts"
                        type="date"
                        value={startDate}
                        onChange={(event) => setStartDate(event.target.value)}
                    />
                    <FTextInput
                        label="Ends (optional)"
                        type="date"
                        min={startDate}
                        value={endDate}
                        onChange={(event) => setEndDate(event.target.value)}
                    />
                </div>
                <Checkbox
                    checked={autoCreate}
                    onChange={(event) => setAutoCreate(event.currentTarget.checked)}
                    label="Create transactions automatically"
                />
            </div>
        </AppDialog>
    );
}
