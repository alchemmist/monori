import { useMemo, useState } from "react";
import { useStore } from "../store.js";
import { orderedGroups, categoriesByGroup } from "../categoryOrder.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FSelect, FTextInput } from "../ui/fields.jsx";
import Txt from "../ui/Txt.jsx";

export function CategoryEditDialog({ category, groups, onClose }) {
    const { patchCategory, createCategory, notify } = useStore();
    const isNew = !category.id;
    const [name, setName] = useState(category.name ?? "");
    const [groupId, setGroupId] = useState(String(category.groupId));
    const [keywords, setKeywords] = useState(category.keywords ?? "");
    const [busy, setBusy] = useState(false);

    const apply = async () => {
        if (!name.trim()) return;
        setBusy(true);
        try {
            if (isNew) {
                await createCategory({ name: name.trim(), groupId: +groupId, keywords });
            } else {
                await patchCategory(category.id, {
                    name: name.trim(),
                    groupId: +groupId,
                    keywords,
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
            onApply={apply}
            applyLoading={busy}
            applyDisabled={!name.trim()}
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
                <Txt tone="secondary" caption>
                    Keywords are matched against transaction descriptions during import, separated
                    by |. First matching category wins.
                </Txt>
            </div>
        </AppDialog>
    );
}

export function CategoryMergeDialog({ category, categories, txCount, onClose }) {
    const { mergeCategory, snapshot, notify } = useStore();
    const [target, setTarget] = useState("");
    const [busy, setBusy] = useState(false);
    const others = useMemo(
        () => categories.filter((c) => c.id !== category.id),
        [categories, category.id],
    );
    const into = others.find((c) => String(c.id) === target);

    // only same-kind groups are offered: merging an income category into an
    // expense one would silently flip the sign of its whole history
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
            .filter((s) => s.options.length);
    }, [snapshot.groups, others, category.groupId]);

    // the merge is irreversible, so the dialog spells out what it will do to the
    // target rather than asking for a blind confirmation
    const addedKeywords = useMemo(() => {
        if (!into) return [];
        const have = new Set(
            String(into.keywords ?? "")
                .split("|")
                .map((k) => k.trim().toLowerCase())
                .filter(Boolean),
        );
        const seen = new Set();
        return String(category.keywords ?? "")
            .split("|")
            .map((k) => k.trim())
            .filter((k) => {
                const key = k.toLowerCase();
                if (!k || have.has(key) || seen.has(key)) return false;
                seen.add(key);
                return true;
            });
    }, [into, category.keywords]);

    const budgetMonths = useMemo(
        () => (snapshot.budgets ?? []).filter((b) => b.categoryId === category.id).length,
        [snapshot.budgets, category.id],
    );

    const apply = async () => {
        if (!into) return;
        setBusy(true);
        try {
            await mergeCategory(category.id, into.id);
            onClose();
        } catch (e) {
            notify({ title: "Failed to merge category", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title={`Merge ${category.name}`}
            onClose={onClose}
            applyText="Merge"
            onApply={apply}
            applyLoading={busy}
            applyDisabled={!into}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <FSelect
                    label="Merge into"
                    value={target}
                    onChange={(v) => setTarget(v ?? "")}
                    data={sections}
                    placeholder="Pick a category"
                    searchable
                />
                {into && (
                    <ul className="cat-merge-plan">
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
                        <li>
                            <b>{category.name}</b> disappears. This cannot be undone.
                        </li>
                    </ul>
                )}
                <Txt tone="secondary" caption>
                    Merging is for duplicates — two categories that mean the same thing. Nothing is
                    deleted except the empty shell of the source.
                </Txt>
            </div>
        </AppDialog>
    );
}

export function CategoryDeleteDialog({ category, categories, txCount, onClose }) {
    const { deleteCategory, notify } = useStore();
    const [target, setTarget] = useState("");
    const [busy, setBusy] = useState(false);
    const others = categories.filter((c) => c.id !== category.id);

    const apply = async () => {
        setBusy(true);
        try {
            await deleteCategory(category.id, target ? +target : undefined);
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
            onApply={apply}
            applyLoading={busy}
            applyDanger
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <Txt block>
                    {txCount > 0
                        ? `${txCount} transactions use this category. Where should they go?`
                        : "No transactions use this category. Its budget history will be removed."}
                </Txt>
                {txCount > 0 && (
                    <FSelect
                        label="Move to"
                        value={target}
                        onChange={(v) => setTarget(v ?? "")}
                        data={[
                            { value: "", label: "Leave uncategorized" },
                            ...others.map((c) => ({ value: String(c.id), label: c.name })),
                        ]}
                    />
                )}
                <Txt tone="secondary" caption>
                    Nothing else is affected: other categories, budgets and years stay exactly as
                    they are.
                </Txt>
            </div>
        </AppDialog>
    );
}
