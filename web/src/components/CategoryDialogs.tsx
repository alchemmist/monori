import { useMemo, useRef, useState } from "react";
import { useStore } from "../store.js";
import { orderedGroups, categoriesByGroup } from "../categoryOrder.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FSelect, FTextInput } from "../ui/fields.jsx";
import Txt from "../ui/Txt.jsx";
import type { Category, CategoryGroup, CategoryPatch } from "../types.js";

export function CategoryEditDialog({
    category,
    groups,
    onClose,
}: {
    category: Partial<Category>;
    groups: CategoryGroup[];
    onClose: () => void;
}) {
    const { patchCategory, createCategory, notify } = useStore();
    const isNew = category.id == null;
    const [name, setName] = useState(category.name ?? "");
    const [groupId, setGroupId] = useState(String(category.groupId));
    const [keywords, setKeywords] = useState(category.keywords ?? "");
    const [goalTarget, setGoalTarget] = useState(
        category.goalTarget == null || category.goalTarget === 0
            ? ""
            : String(category.goalTarget / 100),
    );
    const [goalTargetDate, setGoalTargetDate] = useState(category.goalTargetDate ?? "");
    const [busy, setBusy] = useState(false);
    const goalGroup = groups.find((g) => String(g.id) === groupId)?.kind === "goal";
    const targetKopecks = Math.round(Number(goalTarget.replace(",", ".")) * 100);

    const apply = async () => {
        if (name.trim() === "") return;
        setBusy(true);
        try {
            if (category.id == null) {
                await createCategory({
                    name: name.trim(),
                    groupId: +groupId,
                    keywords,
                    ...(goalGroup
                        ? {
                              goalTarget: targetKopecks,
                              goalTargetDate: goalTargetDate === "" ? null : goalTargetDate,
                          }
                        : {}),
                });
            } else {
                await patchCategory(category.id, {
                    name: name.trim(),
                    groupId: +groupId,
                    keywords,
                    ...(goalGroup ? { goalTarget: targetKopecks, goalTargetDate } : {}),
                });
            }
            onClose();
        } catch (e) {
            notify({
                title: isNew ? "Failed to create category" : "Failed to update category",
                theme: "danger",
                content: String(e),
            });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title={isNew ? "New category" : `Edit ${category.name}`}
            onClose={onClose}
            applyText={isNew ? "Create" : "Save"}
            onApply={() => void apply()}
            applyLoading={busy}
            applyDisabled={!name.trim() || (goalGroup && !(targetKopecks > 0))}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <FTextInput
                    label="Name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoFocus
                />
                <FSelect
                    label="Group"
                    value={groupId}
                    onChange={setGroupId}
                    data={groups.map((g) => ({ value: String(g.id), label: g.name }))}
                />
                <FTextInput
                    label="Keywords"
                    value={keywords}
                    onChange={(e) => setKeywords(e.target.value)}
                    placeholder="Substring|Another substring"
                />
                {goalGroup && (
                    <>
                        <FTextInput
                            label="Target, ₽"
                            value={goalTarget}
                            onChange={(e) => setGoalTarget(e.target.value)}
                            inputMode="decimal"
                        />
                        <FTextInput
                            label="Deadline (optional)"
                            type="date"
                            value={goalTargetDate}
                            onChange={(e) => setGoalTargetDate(e.target.value)}
                        />
                    </>
                )}
                <Txt tone="secondary" caption>
                    Keywords are matched against transaction descriptions during import, separated
                    by |. First matching category wins.
                </Txt>
            </div>
        </AppDialog>
    );
}

export function GoalTargetDialog({
    category,
    onApply,
    onClose,
}: {
    category: Category;
    onApply: (goal: Pick<CategoryPatch, "goalTarget" | "goalTargetDate">) => Promise<void>;
    onClose: () => void;
}) {
    const [goalTarget, setGoalTarget] = useState("");
    const [goalTargetDate, setGoalTargetDate] = useState("");
    const [busy, setBusy] = useState(false);
    const applyingRef = useRef(false);
    const targetKopecks = Math.round(Number(goalTarget.replace(",", ".")) * 100);
    const validTarget = targetKopecks > 0 && Number.isSafeInteger(targetKopecks);

    const apply = async () => {
        if (!validTarget || applyingRef.current) return;
        applyingRef.current = true;
        setBusy(true);
        try {
            await onApply({
                goalTarget: targetKopecks,
                goalTargetDate: goalTargetDate || null,
            });
            onClose();
        } catch {
        } finally {
            applyingRef.current = false;
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title={`Set a goal for ${category.name}`}
            onClose={onClose}
            applyText="Move"
            onApply={() => void apply()}
            applyLoading={busy}
            applyDisabled={busy || !validTarget}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <FTextInput
                    label="Target, ₽"
                    value={goalTarget}
                    onChange={(e) => setGoalTarget(e.target.value)}
                    inputMode="decimal"
                    autoFocus
                />
                <FTextInput
                    label="Deadline (optional)"
                    type="date"
                    value={goalTargetDate}
                    onChange={(e) => setGoalTargetDate(e.target.value)}
                />
            </div>
        </AppDialog>
    );
}

export function CategoryDeleteDialog({
    category,
    categories,
    txCount,
    onClose,
}: {
    category: Category;
    categories: Category[];
    txCount: number;
    onClose: () => void;
}) {
    const { deleteCategory, mergeCategory, snapshot, notify } = useStore();
    if (!snapshot) throw new Error("Category deletion requires a loaded snapshot");
    const [target, setTarget] = useState("");
    const [busy, setBusy] = useState(false);
    const others = useMemo(
        () => categories.filter((c) => c.id !== category.id),
        [categories, category.id],
    );
    const into = others.find((c) => String(c.id) === target);

    // only same-kind groups are offered: moving an income category's history into
    // an expense one would silently flip its sign, and the server refuses it
    const sections = useMemo(() => {
        const groups = orderedGroups(snapshot.groups);
        const kind = groups.find((g) => g.id === category.groupId)?.kind;
        const same = groups.filter((g) => g.kind === kind);
        const byGroup = categoriesByGroup(others, same);
        return same
            .map((g) => ({
                id: g.id,
                group: g.name,
                kind: g.kind,
                options: (byGroup.get(g.id) ?? []).map((c) => ({
                    value: String(c.id),
                    label: c.name,
                })),
            }))
            .filter((s) => s.options.length > 0);
    }, [snapshot.groups, others, category.groupId]);

    // the delete is irreversible, so the dialog spells out what it will do to the
    // target rather than asking for a blind confirmation
    const addedKeywords = useMemo(() => {
        if (into == null) return [];
        const have = new Set(
            into.keywords
                .split("|")
                .map((k) => k.trim().toLowerCase())
                .filter((keyword) => keyword !== ""),
        );
        const seen = new Set<string>();
        return category.keywords
            .split("|")
            .map((k) => k.trim())
            .filter((k) => {
                const key = k.toLowerCase();
                if (k === "" || have.has(key) || seen.has(key)) return false;
                seen.add(key);
                return true;
            });
    }, [into, category.keywords]);

    const budgetMonths = useMemo(
        () => snapshot.budgets.filter((b) => b.categoryId === category.id).length,
        [snapshot.budgets, category.id],
    );

    // picking a target folds this category into that one — the endpoint that
    // carries the keywords and the monthly plan across with the spending
    const apply = async () => {
        setBusy(true);
        try {
            if (into != null) await mergeCategory(category.id, into.id);
            else await deleteCategory(category.id);
            onClose();
        } catch (e) {
            notify({ title: "Failed to delete category", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title={`Delete ${category.name}`}
            onClose={onClose}
            applyText="Delete"
            onApply={() => void apply()}
            applyLoading={busy}
            applyDanger
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <Txt block>
                    {txCount > 0
                        ? `${txCount} transactions use this category. Where should they go?`
                        : "No transactions use this category."}
                </Txt>
                <FSelect
                    label="Move to"
                    value={target}
                    onChange={setTarget}
                    data={[{ value: "", label: "Leave uncategorized" }, ...sections]}
                    searchable
                />
                <ul className="cat-delete-plan">
                    {into != null ? (
                        <>
                            <li>
                                {txCount === 1
                                    ? `1 transaction moves to ${into.name}`
                                    : `${txCount} transactions move to ${into.name}`}
                            </li>
                            <li>
                                {addedKeywords.length
                                    ? `Keywords added to ${into.name}: ${addedKeywords.join(", ")}`
                                    : "No new keywords: the target already covers them"}
                            </li>
                            <li>
                                {budgetMonths
                                    ? `Budgets for ${budgetMonths} month${budgetMonths === 1 ? "" : "s"} are added to the target's plan`
                                    : "No budgets to carry over"}
                            </li>
                        </>
                    ) : (
                        <>
                            {txCount > 0 && (
                                <li>
                                    {txCount === 1
                                        ? "1 transaction is left without a category"
                                        : `${txCount} transactions are left without a category`}
                                </li>
                            )}
                            <li>
                                {budgetMonths
                                    ? `Budgets for ${budgetMonths} month${budgetMonths === 1 ? "" : "s"} are removed`
                                    : "No budget history to remove"}
                            </li>
                        </>
                    )}
                    <li>
                        <b>{category.name}</b> disappears. This cannot be undone.
                    </li>
                </ul>
                <Txt tone="secondary" caption>
                    Only categories of the same kind are offered — moving income history into an
                    expense category would flip its sign.
                </Txt>
            </div>
        </AppDialog>
    );
}
