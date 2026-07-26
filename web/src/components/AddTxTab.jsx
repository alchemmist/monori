import { useEffect, useMemo, useRef, useState } from "react";
import { Button, SegmentedControl } from "@mantine/core";
import { useStore } from "../store.js";
import { orderedGroups, categoriesByGroup } from "../categoryOrder.js";
import { money, parseRub } from "../format.js";
import { FSelect, FTextInput } from "../ui/fields.jsx";
import Tab from "../ui/Tab.jsx";
import Txt from "../ui/Txt.jsx";

const today = () => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return now.toISOString().slice(0, 10);
};

/** How many of the just-entered rows the tab echoes back, newest first. Enough
 * to see that the last few landed, short enough to never take over the panel. */
const RECENT_SHOWN = 5;

/**
 * Manual entry of a transaction, as a side tab rather than a modal: the ledger
 * stays readable behind it and the panel survives navigation, so a whole run of
 * cash spends can be typed in without the form ever closing.
 *
 * "Add" posts the row and clears only what changes between two entries —
 * amount, description and comment. Date, account, direction and category stay
 * put, because entering several rows from one day on one card is the case this
 * panel exists for; focus jumps back to the amount, ready for the next one.
 */
export default function AddTxTab({ onClose }) {
    const { snapshot, addTransaction, notify } = useStore();
    const accounts = useMemo(
        () => (snapshot?.accounts ?? []).filter((a) => !a.archived),
        [snapshot?.accounts],
    );

    const catSections = useMemo(() => {
        const groups = orderedGroups(snapshot?.groups ?? []);
        const byGroup = categoriesByGroup(snapshot?.categories ?? [], groups);
        const sections = [];
        for (const g of groups) {
            const options = (byGroup.get(g.id) ?? [])
                .filter((c) => !c.archived)
                .map((c) => ({ value: String(c.id), label: c.name }));
            if (options.length) sections.push({ id: g.id, group: g.name, kind: g.kind, options });
        }
        return sections;
    }, [snapshot?.groups, snapshot?.categories]);

    const [direction, setDirection] = useState("expense");
    const [amount, setAmount] = useState("");
    const [description, setDescription] = useState("");
    const [date, setDate] = useState(today());
    const [account, setAccount] = useState(accounts[0] ? String(accounts[0].id) : "");
    const [category, setCategory] = useState(null);
    const [comment, setComment] = useState("");
    const [busy, setBusy] = useState(false);
    const [recent, setRecent] = useState([]);
    const amountRef = useRef(null);

    // Restored tabs can mount before the light snapshot arrives. Keep a chosen
    // account, but select the first active one once it is available (or when a
    // previously chosen account was archived/removed).
    useEffect(() => {
        if (accounts.length && (!account || !accounts.some((a) => String(a.id) === account)))
            setAccount(String(accounts[0].id));
    }, [account, accounts]);

    const amountKop = parseRub(amount);
    const valid = !!account && !!date && amountKop != null && amountKop > 0;

    const add = async () => {
        if (!valid || busy) return;
        setBusy(true);
        try {
            const tx = await addTransaction({
                date: `${date}T12:00:00`,
                amount: direction === "income" ? amountKop : -amountKop,
                accountId: +account,
                description: description.trim(),
                categoryId: category ? +category : null,
                comment: comment.trim(),
            });
            setRecent((prev) => [tx, ...prev].slice(0, RECENT_SHOWN));
            setAmount("");
            setDescription("");
            setComment("");
            amountRef.current?.focus();
        } catch (e) {
            notify({ title: "Failed to add the transaction", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    // Enter anywhere in the form adds the row, so a full entry never needs the
    // mouse; the comment field is a plain input, so nothing swallows the key
    const onKeyDown = (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            add();
        }
    };

    return (
        <Tab
            title="Add transaction"
            strip="Add transaction"
            onClose={onClose}
            footer={
                <Button variant="filled" onClick={add} loading={busy} disabled={!valid}>
                    Add
                </Button>
            }
        >
            <div
                style={{ display: "flex", flexDirection: "column", gap: 12 }}
                onKeyDown={onKeyDown}
            >
                <SegmentedControl
                    value={direction}
                    onChange={setDirection}
                    data={[
                        { value: "expense", label: "Expense" },
                        { value: "income", label: "Income" },
                    ]}
                    fullWidth
                />
                <FTextInput
                    ref={amountRef}
                    label="Amount"
                    inputMode="decimal"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    autoFocus
                />
                <FTextInput
                    label="Description"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                />
                <FTextInput
                    label="Date"
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                />
                <FSelect
                    label="Account"
                    value={account || null}
                    onChange={setAccount}
                    data={accounts.map((a) => ({ value: String(a.id), label: a.name }))}
                />
                <FSelect
                    label="Category"
                    searchable
                    placeholder="Uncategorized"
                    value={category}
                    onChange={setCategory}
                    data={[{ value: "", label: "Uncategorized" }, ...catSections]}
                />
                <FTextInput
                    label="Comment"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                />
                {!accounts.length && (
                    <Txt tone="danger" caption>
                        Create an account first — a transaction has to live on one.
                    </Txt>
                )}
                <Txt tone="secondary" caption>
                    Date, account and category stay for the next one.
                </Txt>
                {recent.length > 0 && (
                    <div className="addtx-recent">
                        <Txt tone="secondary" caption>
                            Added in this session
                        </Txt>
                        {recent.map((t) => (
                            <div key={t.id} className="addtx-recent__row">
                                <span className="addtx-recent__desc">{t.description || "—"}</span>
                                <span className={`money num ${t.amount > 0 ? "money_pos" : ""}`}>
                                    {money(t.amount)}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </Tab>
    );
}
