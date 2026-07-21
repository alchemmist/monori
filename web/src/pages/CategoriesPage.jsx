import { useMemo, useRef, useState } from "react";
import { Button, DropdownMenu, Label } from "@gravity-ui/uikit";
import { Plus } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { CategoryEditDialog, CategoryDeleteDialog } from "../components/CategoryDialogs.jsx";
import { GroupEditDialog, GroupDeleteDialog } from "../components/GroupDialogs.jsx";
import "./categories.css";

// match the backend's ORDER BY sort, id — deterministic even when sort is missing
// (demo groups omit it) or tied
const bySortThenId = (a, b) => (a.sort ?? 0) - (b.sort ?? 0) || a.id - b.id;

export default function CategoriesPage() {
    const { snapshot, moveCategory, reorderGroups } = useStore();
    const [dialog, setDialog] = useState(null);
    const [drag, setDrag] = useState(null); // {type:'card'|'col', id}
    const [overGroup, setOverGroup] = useState(null); // group id highlighted as a card drop target
    const [overCol, setOverCol] = useState(null); // {id, side:'before'|'after'} for column reorder
    const boardRef = useRef(null);

    const groups = useMemo(() => [...snapshot.groups].sort(bySortThenId), [snapshot.groups]);

    const catsByGroup = useMemo(() => {
        const m = new Map(groups.map((g) => [g.id, []]));
        for (const c of [...snapshot.categories].sort(bySortThenId)) {
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

    // ---- card drag & drop (move between / reorder within groups) ----
    const cardDropIndex = (colEl, clientY) => {
        const cards = [...colEl.querySelectorAll(".kb-card")];
        for (let i = 0; i < cards.length; i++) {
            const r = cards[i].getBoundingClientRect();
            if (clientY < r.top + r.height / 2) return i;
        }
        return cards.length;
    };

    const onCardDrop = (e, toGroupId) => {
        e.preventDefault();
        setOverGroup(null);
        if (drag?.type !== "card") return;
        const colEl = e.currentTarget.querySelector(".kb-cards");
        const index = colEl ? cardDropIndex(colEl, e.clientY) : 0;
        const cols = new Map(groups.map((g) => [g.id, (catsByGroup.get(g.id) ?? []).slice()]));
        for (const arr of cols.values()) {
            const i = arr.findIndex((c) => c.id === drag.id);
            if (i >= 0) arr.splice(i, 1);
        }
        const moved = snapshot.categories.find((c) => c.id === drag.id);
        cols.get(toGroupId).splice(index, 0, moved);
        const orderedIds = groups.flatMap((g) => cols.get(g.id).map((c) => c.id));
        moveCategory(drag.id, toGroupId, orderedIds);
        setDrag(null);
    };

    // ---- column drag & drop (reorder groups) ----
    const onColDrop = (e, targetId) => {
        e.preventDefault();
        setOverCol(null);
        if (drag?.type !== "col" || drag.id === targetId) {
            setDrag(null);
            return;
        }
        const r = e.currentTarget.getBoundingClientRect();
        const after = e.clientX > r.left + r.width / 2;
        const ids = groups.map((g) => g.id).filter((id) => id !== drag.id);
        let at = ids.indexOf(targetId);
        if (after) at += 1;
        ids.splice(at, 0, drag.id);
        reorderGroups(ids);
        setDrag(null);
    };

    const notify = (t) => useStore.getState().notify(t);

    const catMenu = (c) => [
        { text: "Edit", action: () => setDialog({ type: "cat-edit", category: c }) },
        {
            text: c.archived ? "Unarchive" : "Archive",
            action: () =>
                useStore
                    .getState()
                    .patchCategory(c.id, { archived: !c.archived })
                    .catch((e) =>
                        notify({
                            title: "Failed to update category",
                            theme: "danger",
                            content: String(e),
                        }),
                    ),
        },
        {
            text: "Delete",
            theme: "danger",
            action: () => setDialog({ type: "cat-delete", category: c }),
        },
    ];

    const groupMenu = (g) => [
        { text: "Rename & kind", action: () => setDialog({ type: "group-edit", group: g }) },
        {
            text: "Delete",
            theme: "danger",
            action: () => setDialog({ type: "group-delete", group: g }),
        },
    ];

    return (
        <div className="fade-in">
            <div className="budget-toolbar">
                <h1 className="page-title" style={{ margin: 0 }}>
                    Categories
                </h1>
                <div style={{ flex: 1 }} />
                <NewGroupControl
                    onPick={(kind) => setDialog({ type: "group-edit", group: { kind } })}
                />
                <Button
                    view="action"
                    size="m"
                    onClick={() =>
                        setDialog({ type: "cat-edit", category: { groupId: groups[0]?.id } })
                    }
                    disabled={groups.length === 0}
                >
                    <Plus width={14} height={14} /> New category
                </Button>
            </div>

            <div className="kb-board" ref={boardRef}>
                {groups.map((g) => {
                    const cats = catsByGroup.get(g.id) ?? [];
                    const dropHere = drag?.type === "card" && overGroup === g.id;
                    const colMark =
                        drag?.type === "col" && overCol?.id === g.id ? overCol.side : null;
                    return (
                        <div
                            key={g.id}
                            className={`kb-col kb-col_${g.kind}${dropHere ? " kb-col_drop" : ""}${
                                colMark ? ` kb-col_mark-${colMark}` : ""
                            }${drag?.type === "col" && drag.id === g.id ? " kb-col_dragging" : ""}`}
                            onDragOver={(e) => {
                                if (drag?.type === "card") {
                                    e.preventDefault();
                                    setOverGroup(g.id);
                                } else if (drag?.type === "col" && drag.id !== g.id) {
                                    e.preventDefault();
                                    const r = e.currentTarget.getBoundingClientRect();
                                    setOverCol({
                                        id: g.id,
                                        side: e.clientX > r.left + r.width / 2 ? "after" : "before",
                                    });
                                }
                            }}
                            onDragLeave={(e) => {
                                if (!e.currentTarget.contains(e.relatedTarget)) {
                                    if (drag?.type === "card") setOverGroup(null);
                                    else if (drag?.type === "col") setOverCol(null);
                                }
                            }}
                            onDrop={(e) =>
                                drag?.type === "col" ? onColDrop(e, g.id) : onCardDrop(e, g.id)
                            }
                        >
                            <div
                                className="kb-col__head"
                                draggable
                                onDragStart={(e) => {
                                    setDrag({ type: "col", id: g.id });
                                    e.dataTransfer.effectAllowed = "move";
                                }}
                                onDragEnd={() => {
                                    setDrag(null);
                                    setOverCol(null);
                                }}
                            >
                                <span className="kb-col__name">{g.name}</span>
                                <Label size="xs" theme={g.kind === "income" ? "success" : "danger"}>
                                    {g.kind}
                                </Label>
                                <span className="kb-col__count">{cats.length}</span>
                                <div
                                    style={{ marginLeft: "auto" }}
                                    draggable
                                    onDragStart={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                    }}
                                >
                                    <DropdownMenu size="s" items={groupMenu(g)} />
                                </div>
                            </div>

                            <div className="kb-cards">
                                {cats.map((c) => (
                                    <div
                                        key={c.id}
                                        className={`kb-card${
                                            drag?.type === "card" && drag.id === c.id
                                                ? " kb-card_dragging"
                                                : ""
                                        }`}
                                        draggable
                                        onDragStart={(e) => {
                                            setDrag({ type: "card", id: c.id });
                                            e.dataTransfer.effectAllowed = "move";
                                        }}
                                        onDragEnd={() => {
                                            setDrag(null);
                                            setOverGroup(null);
                                        }}
                                    >
                                        <div className="kb-card__top">
                                            <span className="kb-card__name">{c.name}</span>
                                            {c.archived && (
                                                <Label size="xs" theme="warning">
                                                    arch
                                                </Label>
                                            )}
                                            <span
                                                className="kb-card__usage"
                                                title={`${txCountByCat.get(c.id) ?? 0} transactions`}
                                            >
                                                {txCountByCat.get(c.id) ?? 0}
                                            </span>
                                            <div
                                                className="kb-card__menu"
                                                draggable
                                                onDragStart={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                }}
                                            >
                                                <DropdownMenu size="s" items={catMenu(c)} />
                                            </div>
                                        </div>
                                        {c.keywords && (
                                            <div className="kb-card__kw">
                                                {c.keywords.split("|").filter(Boolean).join(", ")}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>

                            <button
                                className="kb-add-card"
                                onClick={() =>
                                    setDialog({ type: "cat-edit", category: { groupId: g.id } })
                                }
                            >
                                <Plus width={13} height={13} /> Add category
                            </button>
                        </div>
                    );
                })}

                <NewGroupColumn
                    onPick={(kind) => setDialog({ type: "group-edit", group: { kind } })}
                />
            </div>

            {dialog?.type === "cat-edit" && (
                <CategoryEditDialog
                    category={dialog.category}
                    groups={groups}
                    onClose={() => setDialog(null)}
                />
            )}
            {dialog?.type === "cat-delete" && (
                <CategoryDeleteDialog
                    category={dialog.category}
                    categories={snapshot.categories}
                    txCount={txCountByCat.get(dialog.category.id) ?? 0}
                    onClose={() => setDialog(null)}
                />
            )}
            {dialog?.type === "group-edit" && (
                <GroupEditDialog group={dialog.group} onClose={() => setDialog(null)} />
            )}
            {dialog?.type === "group-delete" && (
                <GroupDeleteDialog
                    group={dialog.group}
                    catCount={(catsByGroup.get(dialog.group.id) ?? []).length}
                    onClose={() => setDialog(null)}
                />
            )}
        </div>
    );
}

// hover splits the control into a green Income / red Expense half; clicking a
// half starts a new group of that kind
function NewGroupControl({ onPick }) {
    return (
        <div className="kb-newgroup" title="Create a group">
            <span className="kb-newgroup__label">
                <Plus width={14} height={14} /> New group
            </span>
            <button
                className="kb-newgroup__half kb-newgroup__half_income"
                onClick={() => onPick("income")}
            >
                Income
            </button>
            <button
                className="kb-newgroup__half kb-newgroup__half_expense"
                onClick={() => onPick("expense")}
            >
                Expense
            </button>
        </div>
    );
}

function NewGroupColumn({ onPick }) {
    return (
        <div className="kb-col kb-col_add">
            <span className="kb-col_add__label">
                <Plus width={14} height={14} /> New group
            </span>
            <button
                className="kb-col_add__half kb-col_add__half_income"
                onClick={() => onPick("income")}
            >
                <Plus width={13} height={13} /> Income group
            </button>
            <button
                className="kb-col_add__half kb-col_add__half_expense"
                onClick={() => onPick("expense")}
            >
                <Plus width={13} height={13} /> Expense group
            </button>
        </div>
    );
}
