import { useState } from "react";
import { useStore } from "../store.js";
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
