import { useLayoutEffect, useMemo, useRef, useState } from "react";
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
    const [over, setOver] = useState(null); // {groupId, index} — live card insertion point
    const [overCol, setOverCol] = useState(null); // {id, side:'before'|'after'} for column reorder
    const boardRef = useRef(null);
    const rectsRef = useRef(new Map());
    const animsRef = useRef(new Map());

    // FLIP: slide cards from their previous Y to the new one so neighbours part
    // smoothly as the live-reorder moves them, instead of snapping. Deliberately:
    //  - only the VERTICAL delta is animated — horizontal board scroll changes
    //    every card's left, and animating that made grabbing-after-scroll jump;
    //  - any in-flight FLIP is cancelled BEFORE measuring, so a mid-animation
    //    transform can't compound into the next delta (that made cards fly apart
    //    on fast drags);
    //  - the dragged card is skipped, and it only runs during an active card drag.
    useLayoutEffect(() => {
        const board = boardRef.current;
        if (!board) return;
        const cards = [...board.querySelectorAll(".kb-card[data-id]")];
        for (const el of cards) {
            const a = animsRef.current.get(el.dataset.id);
            if (a) {
                a.cancel();
                animsRef.current.delete(el.dataset.id);
            }
        }
        const next = new Map();
        for (const el of cards) next.set(el.dataset.id, el.getBoundingClientRect().top);
        if (drag?.type === "card") {
            for (const el of cards) {
                const id = el.dataset.id;
                const prev = rectsRef.current.get(id);
                const top = next.get(id);
                if (prev == null || prev === top || el.classList.contains("kb-card_dragging"))
                    continue;
                const anim = el.animate(
                    [{ transform: `translateY(${prev - top}px)` }, { transform: "translateY(0)" }],
                    { duration: 150, easing: "ease" },
                );
                animsRef.current.set(id, anim);
                anim.onfinish = () => animsRef.current.delete(id);
            }
        }
        rectsRef.current = next;
    });

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
    // The dragged card is NOT hidden (display:none aborts the native drag in
    // Chrome). Instead we live-reorder: remove it from its origin and splice it,
    // dimmed, into the hovered column at the target index — it acts as its own
    // placeholder, parting the neighbours right where it will land.
    const previewCats = (groupId) => {
        const base = catsByGroup.get(groupId) ?? [];
        if (drag?.type !== "card") return base;
        const list = base.filter((c) => c.id !== drag.id);
        if (over?.groupId !== groupId) return list;
        const moved = snapshot.categories.find((c) => c.id === drag.id);
        const idx = Math.min(over.index, list.length);
        return [...list.slice(0, idx), moved, ...list.slice(idx)];
    };

    // insertion index among the column's cards, ignoring the one being dragged
    const cardDropIndex = (colEl, clientY) => {
        const cards = [...colEl.querySelectorAll(".kb-card")].filter(
            (el) => +el.dataset.id !== drag.id,
        );
        for (let i = 0; i < cards.length; i++) {
            const r = cards[i].getBoundingClientRect();
            if (clientY < r.top + r.height / 2) return i;
        }
        return cards.length;
    };

    const onCardDragOver = (e, groupId) => {
        if (drag?.type !== "card") return;
        e.preventDefault();
        const colEl = e.currentTarget.querySelector(".kb-cards");
        const index = colEl ? cardDropIndex(colEl, e.clientY) : 0;
        setOver((o) => (o && o.groupId === groupId && o.index === index ? o : { groupId, index }));
    };

    const onCardDrop = (e, toGroupId) => {
        e.preventDefault();
        if (drag?.type !== "card") return;
        const target = over?.groupId ?? toGroupId;
        const index = over?.index ?? 0;
        const cols = new Map(
            groups.map((g) => [
                g.id,
                (catsByGroup.get(g.id) ?? []).filter((c) => c.id !== drag.id),
            ]),
        );
        const moved = snapshot.categories.find((c) => c.id === drag.id);
        const dest = cols.get(target);
        dest.splice(Math.min(index, dest.length), 0, moved);
        const orderedIds = groups.flatMap((g) => cols.get(g.id).map((c) => c.id));
        moveCategory(drag.id, target, orderedIds);
        setDrag(null);
        setOver(null);
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

    // the card being dragged stays mounted and visible (dimmed via kb-card_dragging)
    // so it reads as the live placeholder at the drop point
    const renderCard = (c, groupId) => (
        <div
            key={c.id}
            data-id={c.id}
            className={`kb-card${drag?.type === "card" && drag.id === c.id ? " kb-card_dragging" : ""}`}
            draggable
            onDragStart={(e) => {
                const list = catsByGroup.get(groupId) ?? [];
                setDrag({ type: "card", id: c.id });
                setOver({ groupId, index: list.findIndex((x) => x.id === c.id) });
                e.dataTransfer.effectAllowed = "move";
            }}
            onDragEnd={() => {
                setDrag(null);
                setOver(null);
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
    );

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

            <div className={`kb-board${drag ? " kb-board_dragging" : ""}`} ref={boardRef}>
                {groups.map((g) => {
                    const cats = catsByGroup.get(g.id) ?? [];
                    const shown = previewCats(g.id);
                    const colMark =
                        drag?.type === "col" && overCol?.id === g.id ? overCol.side : null;
                    return (
                        <div
                            key={g.id}
                            className={`kb-col kb-col_${g.kind}${
                                colMark ? ` kb-col_mark-${colMark}` : ""
                            }${drag?.type === "col" && drag.id === g.id ? " kb-col_dragging" : ""}`}
                            onDragOver={(e) => {
                                if (drag?.type === "card") {
                                    onCardDragOver(e, g.id);
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
                                // keep the card's `over` until another column claims it, so the
                                // dragged card doesn't vanish mid-transit; only clear col marker
                                if (
                                    drag?.type === "col" &&
                                    !e.currentTarget.contains(e.relatedTarget)
                                ) {
                                    setOverCol(null);
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

                            <div className="kb-cards">{shown.map((c) => renderCard(c, g.id))}</div>

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
