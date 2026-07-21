import { useMemo, useState } from "react";
import { Button, DropdownMenu, Label } from "@gravity-ui/uikit";
import { Plus } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { CategoryEditDialog, CategoryDeleteDialog } from "../components/CategoryDialogs.jsx";
import "./categories.css";

const KIND_LABEL = { expense: "Expense", income: "Income" };

export default function CategoriesPage() {
    const { snapshot, notify } = useStore();
    const [dialog, setDialog] = useState(null); // {type: 'edit'|'delete', category}

    const groups = useMemo(
        () => [...snapshot.groups].sort((a, b) => a.sort - b.sort),
        [snapshot.groups],
    );

    const catsByGroup = useMemo(() => {
        const m = new Map(groups.map((g) => [g.id, []]));
        for (const c of [...snapshot.categories].sort((a, b) => a.sort - b.sort)) {
            if (m.has(c.groupId)) m.get(c.groupId).push(c);
        }
        return m;
    }, [snapshot.categories, groups]);

    const txCountByCat = useMemo(() => {
        const m = new Map();
        for (const t of snapshot.transactions) {
            if (t.categoryId != null) m.set(t.categoryId, (m.get(t.categoryId) ?? 0) + 1);
        }
        return m;
    }, [snapshot.transactions]);

    const toggleArchived = (c) =>
        useStore
            .getState()
            .patchCategory(c.id, { archived: !c.archived })
            .catch((e) =>
                notify({
                    title: "Failed to update category",
                    theme: "danger",
                    content: String(e),
                }),
            );

    const catMenu = (c) => [
        { text: "Edit", action: () => setDialog({ type: "edit", category: c }) },
        {
            text: c.archived ? "Unarchive" : "Archive",
            action: () => toggleArchived(c),
        },
        {
            text: "Delete",
            theme: "danger",
            action: () => setDialog({ type: "delete", category: c }),
        },
    ];

    return (
        <div className="fade-in">
            <div className="budget-toolbar">
                <h1 className="page-title" style={{ margin: 0 }}>
                    Categories
                </h1>
                <div style={{ flex: 1 }} />
                <Button
                    view="action"
                    size="m"
                    onClick={() =>
                        setDialog({ type: "edit", category: { groupId: groups[0]?.id } })
                    }
                    disabled={groups.length === 0}
                >
                    <Plus width={14} height={14} /> New category
                </Button>
            </div>

            <div className="cat-groups">
                {groups.map((g) => {
                    const cats = catsByGroup.get(g.id) ?? [];
                    return (
                        <div key={g.id} className="cat-group">
                            <div className="cat-group__head">
                                <span className="cat-group__name">{g.name}</span>
                                <Label size="xs" theme="unknown">
                                    {KIND_LABEL[g.kind] ?? g.kind}
                                </Label>
                                <span className="cat-group__count">{cats.length}</span>
                                <div style={{ flex: 1 }} />
                                <Button
                                    view="flat"
                                    size="s"
                                    onClick={() =>
                                        setDialog({ type: "edit", category: { groupId: g.id } })
                                    }
                                >
                                    <Plus width={14} height={14} /> Add
                                </Button>
                            </div>
                            <div className="card cat-list">
                                {cats.length === 0 && (
                                    <div className="cat-list__empty">No categories yet</div>
                                )}
                                {cats.map((c) => (
                                    <div key={c.id} className="cat-list-row">
                                        <div className="cat-list-row__main">
                                            <span className="cat-list-row__name">{c.name}</span>
                                            {c.archived && (
                                                <Label size="xs" theme="warning">
                                                    archived
                                                </Label>
                                            )}
                                            {c.keywords && (
                                                <span className="cat-list-row__keywords">
                                                    {c.keywords.split("|").filter(Boolean).join(", ")}
                                                </span>
                                            )}
                                        </div>
                                        <span className="cat-list-row__count num">
                                            {txCountByCat.get(c.id) ?? 0} tx
                                        </span>
                                        <div className="cat-list-row__actions">
                                            <DropdownMenu size="s" items={catMenu(c)} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    );
                })}
            </div>

            {dialog?.type === "edit" && (
                <CategoryEditDialog
                    category={dialog.category}
                    groups={groups}
                    onClose={() => setDialog(null)}
                />
            )}
            {dialog?.type === "delete" && (
                <CategoryDeleteDialog
                    category={dialog.category}
                    categories={snapshot.categories}
                    txCount={txCountByCat.get(dialog.category.id) ?? 0}
                    onClose={() => setDialog(null)}
                />
            )}
        </div>
    );
}
