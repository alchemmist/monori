import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Modal } from "@mantine/core";
import { Plus, TrashBin } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { FTextInput } from "../ui/fields.jsx";
import InlineSelect from "../ui/InlineSelect.jsx";
import { amountInput, money, parseRub } from "../format.js";
import { signedSplitAmount } from "../engine/splitAmounts.js";
import { PALETTE } from "../pages/chartTheme.js";

const blankPart = () => ({ categoryId: null, amount: "", comment: "" });

const evenAmounts = (total, count) => {
    const base = Math.trunc(Math.abs(total) / count);
    return Array.from({ length: count }, (_, index) =>
        index === count - 1 ? Math.abs(total) - base * (count - 1) : base,
    );
};

function AllocationBar({ amounts, total, onChange }) {
    const boundaries = amounts
        .slice(0, -1)
        .map((_, index) => amounts.slice(0, index + 1).reduce((sum, amount) => sum + amount, 0));
    const stops = amounts.reduce(
        (result, amount, index) => {
            const from = result.position;
            const to = from + (amount / total) * 100;
            result.colors.push(
                `${PALETTE[index % PALETTE.length]} ${from}%`,
                `${PALETTE[index % PALETTE.length]} ${to}%`,
            );
            result.position = to;
            return result;
        },
        { colors: [], position: 0 },
    );

    const moveBoundary = (index, value) => {
        const previous = index === 0 ? 0 : boundaries[index - 1];
        const next = index === boundaries.length - 1 ? total : boundaries[index + 1];
        const boundary = Math.max(previous + 1, Math.min(next - 1, value));
        const nextAmounts = [...amounts];
        nextAmounts[index] = boundary - previous;
        nextAmounts[index + 1] = next - boundary;
        onChange(nextAmounts);
    };

    return (
        <div
            className="split-allocation"
            style={{ background: `linear-gradient(90deg, ${stops.colors.join(", ")})` }}
        >
            {boundaries.map((boundary, index) => (
                <input
                    key={index}
                    className="split-allocation__range"
                    type="range"
                    aria-label={`Boundary between parts ${index + 1} and ${index + 2}`}
                    min={1}
                    max={total - 1}
                    step={1}
                    value={boundary}
                    onChange={(event) => moveBoundary(index, Number(event.target.value))}
                />
            ))}
        </div>
    );
}

export default function SplitTransactionDialog({ transaction, onClose }) {
    const { snapshot, replaceTransactionSplits, notify } = useStore();
    const [parts, setParts] = useState([blankPart(), blankPart()]);
    const [saving, setSaving] = useState(false);
    const lastValidAllocation = useRef(null);

    useEffect(() => {
        if (!transaction) return;
        setParts(
            transaction.splits?.length
                ? transaction.splits.map((part) => ({
                      categoryId: part.categoryId,
                      amount: amountInput(Math.abs(part.amount)),
                      comment: part.comment ?? "",
                  }))
                : evenAmounts(transaction.amount, 2).map((amount) => ({
                      ...blankPart(),
                      amount: amountInput(amount),
                  })),
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
    const totalMagnitude = Math.abs(transaction.amount);
    const parsed = parts.map((part) => {
        const amount = parseRub(part.amount);
        return amount == null ? null : Math.abs(amount);
    });
    const assigned = parsed.reduce((sum, amount) => sum + (amount ?? 0), 0);
    const remainder = totalMagnitude - assigned;
    const allocationValid =
        remainder === 0 && parsed.every((amount) => amount != null && amount !== 0);
    if (allocationValid) {
        lastValidAllocation.current = { transactionId: transaction.id, amounts: parsed };
    }
    const barAmounts =
        lastValidAllocation.current?.transactionId === transaction.id
            ? lastValidAllocation.current.amounts
            : evenAmounts(totalMagnitude, parts.length);
    const valid =
        parts.length >= 2 &&
        allocationValid &&
        parts.every(
            (part, index) =>
                part.categoryId != null && parsed[index] != null && parsed[index] !== 0,
        );

    const change = (index, patch) =>
        setParts((current) =>
            current.map((part, i) => (i === index ? { ...part, ...patch } : part)),
        );
    const changeAmount = (index, value) => {
        const amount = parseRub(value);
        if (amount == null || amount === 0) {
            change(index, { amount: value });
            return;
        }
        const magnitude = Math.abs(amount);
        const recipient = index === parts.length - 1 ? index - 1 : parts.length - 1;
        const basis =
            lastValidAllocation.current?.transactionId === transaction.id
                ? lastValidAllocation.current.amounts
                : parsed;
        const previous = basis[index] ?? 0;
        const recipientAmount = (basis[recipient] ?? 0) - (magnitude - previous);
        if (recipientAmount <= 0) {
            change(index, { amount: value });
            return;
        }
        setParts((current) =>
            current.map((part, partIndex) => {
                if (partIndex === index) return { ...part, amount: value };
                if (partIndex === recipient)
                    return { ...part, amount: amountInput(recipientAmount) };
                return part;
            }),
        );
    };
    const splitEvenly = () => {
        const amounts = evenAmounts(totalMagnitude, parts.length);
        setParts((current) =>
            current.map((part, index) => {
                return { ...part, amount: amountInput(amounts[index]) };
            }),
        );
    };
    const changeAllocations = (amounts) =>
        setParts((current) =>
            current.map((part, index) => ({ ...part, amount: amountInput(amounts[index]) })),
        );
    const addPart = () => {
        const amounts = evenAmounts(totalMagnitude, parts.length + 1);
        setParts((current) => [
            ...current.map((part, index) => ({ ...part, amount: amountInput(amounts[index]) })),
            { ...blankPart(), amount: amountInput(amounts.at(-1)) },
        ]);
    };
    const removePart = (index) => {
        const removed = parsed[index] ?? 0;
        setParts((current) => {
            const next = current.filter((_, partIndex) => partIndex !== index);
            const recipient = Math.min(index, next.length - 1);
            return next.map((part, partIndex) =>
                partIndex === recipient
                    ? {
                          ...part,
                          amount: amountInput(Math.abs(parseRub(part.amount) ?? 0) + removed),
                      }
                    : part,
            );
        });
    };
    const save = async () => {
        setSaving(true);
        try {
            await replaceTransactionSplits(
                transaction.id,
                parts.map((part, index) => ({
                    categoryId: part.categoryId,
                    amount: signedSplitAmount(parsed[index], transaction.amount),
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
            <AllocationBar
                amounts={barAmounts}
                total={totalMagnitude}
                onChange={changeAllocations}
            />
            <div className="split-editor__parts">
                {parts.map((part, index) => (
                    <div
                        className="split-editor__part"
                        key={index}
                        style={{ "--split-color": PALETTE[index % PALETTE.length] }}
                    >
                        <span className="split-editor__swatch" aria-hidden="true" />
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
                            onChange={(event) => changeAmount(index, event.target.value)}
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
                            onClick={() => removePart(index)}
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
                <Button variant="default" leftSection={<Plus width={14} />} onClick={addPart}>
                    Add part
                </Button>
                <Button variant="default" onClick={splitEvenly}>
                    Split evenly
                </Button>
                {transaction.splits?.length > 0 && (
                    <Button
                        className="split-editor__remove"
                        variant="subtle"
                        color="red"
                        loading={saving}
                        onClick={removeSplit}
                    >
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
