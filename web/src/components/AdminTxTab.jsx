import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Checkbox } from "@mantine/core";
import { api } from "../api.js";
import { money } from "../format.js";
import Tab from "../ui/Tab.jsx";
import Txt from "../ui/Txt.jsx";
import { FSelect } from "../ui/fields.jsx";
import { showToast } from "../ui/notify.js";
import { useStore } from "../store.js";

const PAGE = 1000;
const ALL = "all";

/* Bulk operations on one user's transactions, docked as a Tab so the admin
 * page stays usable while working through a selection: filter by account,
 * tick rows (or everything visible), delete the whole selection at once. */
export default function AdminTxTab({ user, onClose }) {
    const [rows, setRows] = useState(null);
    const [filter, setFilter] = useState(ALL);
    const [selected, setSelected] = useState(() => new Set());
    const [busy, setBusy] = useState(false);
    const [arming, setArming] = useState(false);

    const load = useCallback(async () => {
        const all = [];
        for (let offset = 0; ; offset += PAGE) {
            const page = await api.adminUserTransactions(user.id, { limit: PAGE, offset });
            all.push(...page);
            if (page.length < PAGE) break;
        }
        return all;
    }, [user.id]);

    useEffect(() => {
        setRows(null);
        setSelected(new Set());
        load()
            .then(setRows)
            .catch((e) =>
                showToast({
                    title: "Failed to load transactions",
                    content: e.message,
                    theme: "danger",
                }),
            );
    }, [load]);

    const accountNames = useMemo(
        () => [...new Set((rows ?? []).map((r) => r.account))].sort(),
        [rows],
    );
    const visible = useMemo(
        () => (rows ?? []).filter((r) => filter === ALL || r.account === filter),
        [rows, filter],
    );
    const allVisibleSelected = visible.length > 0 && visible.every((r) => selected.has(r.id));

    const toggleRow = (id) => {
        setArming(false);
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const toggleAllVisible = () => {
        setArming(false);
        setSelected((prev) => {
            const next = new Set(prev);
            if (allVisibleSelected) for (const r of visible) next.delete(r.id);
            else for (const r of visible) next.add(r.id);
            return next;
        });
    };

    const removeSelected = async () => {
        if (!arming) {
            setArming(true);
            return;
        }
        setBusy(true);
        try {
            const { deleted } = await api.adminDeleteUserTransactions(user.id, [...selected]);
            showToast({
                title: `Deleted ${deleted} transactions`,
                content: user.email,
                theme: "success",
            });
            setSelected(new Set());
            setArming(false);
            setRows(await load());
            useStore.getState().bumpAdminTick();
        } catch (e) {
            showToast({ title: "Delete failed", content: e.message, theme: "danger" });
        } finally {
            setBusy(false);
        }
    };

    const footer = (
        <>
            <Txt tone="secondary" style={{ marginRight: "auto", alignSelf: "center" }}>
                {selected.size} selected
            </Txt>
            <Button
                size="l"
                variant="filled"
                color="red"
                disabled={selected.size === 0}
                loading={busy}
                onClick={removeSelected}
            >
                {arming ? `Delete ${selected.size} — sure?` : "Delete selected"}
            </Button>
        </>
    );

    return (
        <Tab
            title={`Transactions — ${user.email}`}
            strip="Transactions"
            onClose={onClose}
            footer={footer}
        >
            <FSelect
                label="Account"
                value={filter}
                onChange={(v) => {
                    setFilter(v ?? ALL);
                    setArming(false);
                }}
                data={[
                    { value: ALL, label: "All accounts" },
                    ...accountNames.map((n) => ({ value: n, label: n })),
                ]}
            />
            {rows === null ? (
                <Txt tone="secondary">Loading…</Txt>
            ) : (
                <>
                    <Checkbox
                        size="sm"
                        checked={allVisibleSelected}
                        onChange={toggleAllVisible}
                        label={`Select all visible (${visible.length})`}
                    />
                    <table className="admin-table admin-table_compact">
                        <tbody>
                            {visible.map((t) => (
                                <tr key={t.id} onClick={() => toggleRow(t.id)}>
                                    <td>
                                        <Checkbox
                                            size="xs"
                                            checked={selected.has(t.id)}
                                            onChange={() => toggleRow(t.id)}
                                            onClick={(e) => e.stopPropagation()}
                                        />
                                    </td>
                                    <td className="num">{t.date.slice(0, 10)}</td>
                                    <td>{t.description || t.category || "—"}</td>
                                    <td
                                        className="num"
                                        style={{
                                            color: t.amount >= 0 ? "var(--m-income)" : undefined,
                                        }}
                                    >
                                        {money(t.amount)}
                                    </td>
                                </tr>
                            ))}
                            {visible.length === 0 && (
                                <tr>
                                    <td className="admin-empty">No transactions</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </>
            )}
        </Tab>
    );
}
