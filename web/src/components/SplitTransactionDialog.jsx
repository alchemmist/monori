import { useEffect, useMemo, useState } from "react";
import { Button, Modal } from "@mantine/core";
import { Plus, TrashBin } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { FTextInput } from "../ui/fields.jsx";
import InlineSelect from "../ui/InlineSelect.jsx";
import { money, parseRub } from "../format.js";

const blankPart = () => ({ categoryId: null, amount: "", comment: "" });

export default function SplitTransactionDialog({ transaction, onClose }) {
    const { snapshot, replaceTransactionSplits, notify } = useStore();
    const [parts, setParts] = useState([blankPart(), blankPart()]);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (!transaction) return;
        setParts(
            transaction.splits?.length
                ? transaction.splits.map((part) => ({
                      categoryId: part.categoryId,
                      amount: String(part.amount / 100),
                      comment: part.comment ?? "",
                  }))
                : [blankPart(), blankPart()],
        );
    }, [transaction]);

    const categoryData = useMemo(() => {
        if (!transaction) return [];
        const wanted = transaction.amount < 0 ? "expense" : "income";
        return snapshot.groups
            .filter((group) => group.kind === wanted)
            .map((group) => ({
                group: group.name,
                options: snapshot.categories
                    .filter((category) => category.groupId === group.id && !category.archived)
                    .map((category) => ({ value: String(category.id), label: category.name })),
            }))
            .filter((section) => section.options.length);
    }, [snapshot.categories, snapshot.groups, transaction]);

    if (!transaction) return null;
    const parsed = parts.map((part) => parseRub(part.amount));
    const assigned = parsed.reduce((sum, amount) => sum + (amount ?? 0), 0);
    const remainder = transaction.amount - assigned;
    const valid =
        parts.length >= 2 &&
        remainder === 0 &&
        parts.every(
            (part, index) =>
                part.categoryId != null &&
                parsed[index] != null &&
                parsed[index] !== 0 &&
                parsed[index] > 0 === transaction.amount > 0,
        );

    const change = (index, patch) =>
        setParts((current) =>
            current.map((part, i) => (i === index ? { ...part, ...patch } : part)),
        );
    const assignRemainder = () => {
        if (!remainder) return;
        const index = parts.length - 1;
        change(index, { amount: String(((parsed[index] ?? 0) + remainder) / 100) });
    };
    const splitEvenly = () => {
        const base = Math.trunc(transaction.amount / parts.length);
        let left = transaction.amount;
        setParts((current) =>
            current.map((part, index) => {
                const amount = index === current.length - 1 ? left : base;
                left -= amount;
                return { ...part, amount: String(amount / 100) };
            }),
        );
    };
    const save = async () => {
        setSaving(true);
        try {
            await replaceTransactionSplits(
                transaction.id,
                parts.map((part, index) => ({
                    categoryId: part.categoryId,
                    amount: parsed[index],
                    comment: part.comment.trim(),
                })),
            );
            notify({ title: "Transaction split", theme: "success" });
            onClose();
        } catch (error) {
            notify({
                title: "Failed to split transaction",
                content: String(error),
                theme: "danger",
            });
        } finally {
            setSaving(false);
        }
    };
    const removeSplit = async () => {
        setSaving(true);
        try {
            await replaceTransactionSplits(transaction.id, []);
            notify({ title: "Split removed", theme: "success" });
            onClose();
        } catch (error) {
            notify({ title: "Failed to remove split", content: String(error), theme: "danger" });
        } finally {
            setSaving(false);
        }
    };

    return (
        <Modal
            opened
            onClose={onClose}
            title={`Split · ${transaction.description || "Transaction"}`}
            size="lg"
        >
            <div className="split-editor__summary">
                <span>Total</span>
                <strong className="num">{money(transaction.amount)}</strong>
            </div>
            <div className="split-editor__parts">
                {parts.map((part, index) => (
                    <div className="split-editor__part" key={index}>
                        <InlineSelect
                            searchable
                            placeholder="Category"
                            value={part.categoryId == null ? null : String(part.categoryId)}
                            onChange={(value) =>
                                change(index, { categoryId: value ? +value : null })
                            }
                            data={categoryData}
                        />
                        <FTextInput
                            aria-label={`Part ${index + 1} amount`}
                            value={part.amount}
                            onChange={(event) => change(index, { amount: event.target.value })}
                            placeholder="0.00"
                        />
                        <FTextInput
                            aria-label={`Part ${index + 1} comment`}
                            value={part.comment}
                            onChange={(event) => change(index, { comment: event.target.value })}
                            placeholder="Comment"
                        />
                        <Button
                            variant="subtle"
                            aria-label={`Remove part ${index + 1}`}
                            disabled={parts.length <= 2}
                            onClick={() =>
                                setParts((current) => current.filter((_, i) => i !== index))
                            }
                        >
                            <TrashBin width={14} />
                        </Button>
                    </div>
                ))}
            </div>
            <div
                className={`split-editor__remainder${remainder === 0 ? " split-editor__remainder_done" : ""}`}
            >
                {remainder === 0 ? "Fully assigned" : `${money(remainder)} left to assign`}
            </div>
            <div className="split-editor__actions">
                <Button
                    variant="default"
                    leftSection={<Plus width={14} />}
                    onClick={() => setParts((current) => [...current, blankPart()])}
                >
                    Add part
                </Button>
                <Button variant="default" onClick={splitEvenly}>
                    Split evenly
                </Button>
                <Button variant="default" disabled={!remainder} onClick={assignRemainder}>
                    Assign remainder to last
                </Button>
                <div style={{ flex: 1 }} />
                {transaction.splits?.length > 0 && (
                    <Button variant="subtle" color="red" loading={saving} onClick={removeSplit}>
                        Remove split
                    </Button>
                )}
                <Button loading={saving} disabled={!valid} onClick={save}>
                    Save split
                </Button>
            </div>
        </Modal>
    );
}
