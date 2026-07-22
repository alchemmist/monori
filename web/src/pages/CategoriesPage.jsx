import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Button } from "@mantine/core";
import RowMenu from "../ui/RowMenu.jsx";
import Tag from "../ui/Tag.jsx";
import { Plus } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { orderedGroups, categoriesByGroup } from "../categoryOrder.js";
import { CategoryEditDialog, CategoryDeleteDialog } from "../components/CategoryDialogs.jsx";
import { GroupEditDialog, GroupDeleteDialog } from "../components/GroupDialogs.jsx";
import "./categories.css";

const DRAG_THRESHOLD = 5;
const EDGE = 80;
const EDGE_SPEED = 16;

export default function CategoriesPage() {
    const { snapshot, moveCategory, reorderGroups } = useStore();
    const [dialog, setDialog] = useState(null);
    const [drag, setDrag] = useState(null); // {type:'card'|'col', id, x, y, w} — floating clone
    const [over, setOver] = useState(null); // card: {groupId,index}; col: {index}
    const boardRef = useRef(null);
    const pressRef = useRef(null);
    const dragRef = useRef(null);
    const overRef = useRef(null);
    const cardTopsRef = useRef(new Map());
    const colLeftsRef = useRef(new Map());
    const scrollRef = useRef({ winY: 0, boardX: 0 });
    const animsRef = useRef(new Map());
    const handlersRef = useRef({});

    // FLIP: slide cards (vertically) and columns (horizontally) from their previous
    // position to the new one so neighbours part smoothly as the live-reorder moves
    // them, instead of snapping. Deliberately:
    //  - any in-flight FLIP is cancelled BEFORE measuring, so a mid-animation
    //    transform can't compound into the next delta (that made cards fly apart
    //    on fast drags);
    //  - deltas caused purely by auto-scroll are subtracted out — without that,
    //    scrolling the board mid-drag makes every element fake-slide;
    //  - the dragged element's ghost is skipped so the drop slot moves instantly.
    useLayoutEffect(() => {
        const board = boardRef.current;
        if (!board) return;
        for (const a of animsRef.current.values()) a.cancel();
        animsRef.current.clear();
        const cards = [...board.querySelectorAll(".kb-card[data-id]")];
        const cols = [...board.querySelectorAll(".kb-col[data-gid]")];
        const nextTops = new Map();
        for (const el of cards) nextTops.set(el.dataset.id, el.getBoundingClientRect().top);
        const nextLefts = new Map();
        for (const el of cols) nextLefts.set(el.dataset.gid, el.getBoundingClientRect().left);
        const winY = window.scrollY;
        const boardX = board.scrollLeft;
        const scrollDy = winY - scrollRef.current.winY;
        const scrollDx = boardX - scrollRef.current.boardX;
        if (drag?.type === "card") {
            for (const el of cards) {
                const id = el.dataset.id;
                const prev = cardTopsRef.current.get(id);
                const top = nextTops.get(id);
                if (prev == null || el.classList.contains("kb-card_ghost")) continue;
                const dy = prev - top - scrollDy;
                if (!dy) continue;
                const anim = el.animate(
                    [{ transform: `translateY(${dy}px)` }, { transform: "translateY(0)" }],
                    { duration: 150, easing: "ease" },
                );
                animsRef.current.set(`c${id}`, anim);
                anim.onfinish = () => animsRef.current.delete(`c${id}`);
            }
        }
        if (drag?.type === "col") {
            for (const el of cols) {
                const gid = el.dataset.gid;
                const prev = colLeftsRef.current.get(gid);
                const left = nextLefts.get(gid);
                if (prev == null || el.classList.contains("kb-col_ghost")) continue;
                const dx = prev - left - scrollDx;
                if (!dx) continue;
                const anim = el.animate(
                    [{ transform: `translateX(${dx}px)` }, { transform: "translateX(0)" }],
                    { duration: 170, easing: "ease" },
                );
                animsRef.current.set(`g${gid}`, anim);
                anim.onfinish = () => animsRef.current.delete(`g${gid}`);
            }
        }
        cardTopsRef.current = nextTops;
        colLeftsRef.current = nextLefts;
        scrollRef.current = { winY, boardX };
    });

    const groups = useMemo(() => orderedGroups(snapshot), [snapshot]);

    const catsByGroup = useMemo(() => categoriesByGroup(snapshot, groups), [snapshot, groups]);

    const txCountByCat = useMemo(() => {
        const m = new Map();
        for (const t of snapshot.transactions) {
            if (t.categoryId != null) m.set(t.categoryId, (m.get(t.categoryId) ?? 0) + 1);
        }
        return m;
    }, [snapshot.transactions]);

    // live previews: the dragged card/column is spliced, as a dashed ghost slot,
    // into the hovered position — it acts as its own placeholder, parting the
    // neighbours right where it will land
    const previewCats = (groupId) => {
        const base = catsByGroup.get(groupId) ?? [];
        if (drag?.type !== "card") return base;
        const list = base.filter((c) => c.id !== drag.id);
        if (over?.groupId !== groupId) return list;
        const moved = snapshot.categories.find((c) => c.id === drag.id);
        const idx = Math.min(over.index, list.length);
        return [...list.slice(0, idx), moved, ...list.slice(idx)];
    };

    const shownGroups = useMemo(() => {
        if (drag?.type !== "col" || over?.index == null) return groups;
        const rest = groups.filter((g) => g.id !== drag.id);
        const moved = groups.find((g) => g.id === drag.id);
        const idx = Math.min(over.index, rest.length);
        return [...rest.slice(0, idx), moved, ...rest.slice(idx)];
    }, [groups, drag, over]);

    // ---- pointer-based drag & drop (cards and columns) ----
    // Hand-rolled on pointer events instead of native HTML5 DnD: the browser ghost,
    // frozen cursors and missing edge auto-scroll made the native version unpleasant.
    const startPress = (e, info) => {
        if (e.button !== 0) return;
        if (e.pointerType !== "mouse" && e.pointerType !== "pen") return;
        if (e.target.closest("button, a, input, [role='menuitem']")) return;
        e.preventDefault();
        pressRef.current = { ...info, startX: e.clientX, startY: e.clientY };
    };

    const cardDropIndex = (colEl, clientY) => {
        const els = [...colEl.querySelectorAll(".kb-card")].filter(
            (el) => +el.dataset.id !== dragRef.current.id,
        );
        for (let i = 0; i < els.length; i++) {
            const r = els[i].getBoundingClientRect();
            if (clientY < r.top + r.height / 2) return i;
        }
        return els.length;
    };

    const updateOver = (x, y) => {
        const d = dragRef.current;
        const board = boardRef.current;
        if (!d || !board) return;
        const cols = [...board.querySelectorAll(".kb-col[data-gid]")];
        if (!cols.length) return;
        if (d.type === "card") {
            let target = null;
            let best = Infinity;
            for (const el of cols) {
                const r = el.getBoundingClientRect();
                const dist = x < r.left ? r.left - x : x > r.right ? x - r.right : 0;
                if (dist < best) {
                    best = dist;
                    target = el;
                }
            }
            const groupId = +target.dataset.gid;
            const index = cardDropIndex(target.querySelector(".kb-cards"), y);
            if (overRef.current?.groupId !== groupId || overRef.current?.index !== index) {
                overRef.current = { groupId, index };
                setOver(overRef.current);
            }
        } else {
            const others = cols.filter((el) => +el.dataset.gid !== d.id);
            let index = others.length;
            for (let i = 0; i < others.length; i++) {
                const r = others[i].getBoundingClientRect();
                if (x < r.left + r.width / 2) {
                    index = i;
                    break;
                }
            }
            if (overRef.current?.index !== index) {
                overRef.current = { index };
                setOver({ index });
            }
        }
    };

    const autoScrollTick = () => {
        const d = dragRef.current;
        if (!d) return;
        const board = boardRef.current;
        if (board) {
            const r = board.getBoundingClientRect();
            let moved = false;
            if (d.px < r.left + EDGE) {
                board.scrollLeft -= Math.ceil(((r.left + EDGE - d.px) / EDGE) * EDGE_SPEED);
                moved = true;
            } else if (d.px > r.right - EDGE) {
                board.scrollLeft += Math.ceil(((d.px - (r.right - EDGE)) / EDGE) * EDGE_SPEED);
                moved = true;
            }
            if (d.py < EDGE) {
                window.scrollBy(0, -12);
                moved = true;
            } else if (d.py > window.innerHeight - EDGE) {
                window.scrollBy(0, 12);
                moved = true;
            }
            if (moved) updateOver(d.px, d.py);
        }
        d.raf = requestAnimationFrame(autoScrollTick);
    };

    const beginDrag = (e) => {
        const press = pressRef.current;
        const src = press.type === "card" ? press.el : press.el.closest(".kb-col");
        if (!src) return;
        const r = src.getBoundingClientRect();
        dragRef.current = {
            type: press.type,
            id: press.id,
            dx: press.startX - r.left,
            dy: press.startY - r.top,
            px: e.clientX,
            py: e.clientY,
            raf: 0,
        };
        if (press.type === "card") {
            const cat = snapshot.categories.find((c) => c.id === press.id);
            const list = catsByGroup.get(cat.groupId) ?? [];
            overRef.current = {
                groupId: cat.groupId,
                index: Math.max(
                    0,
                    list.findIndex((c) => c.id === press.id),
                ),
            };
        } else {
            overRef.current = {
                index: Math.max(
                    0,
                    groups.findIndex((g) => g.id === press.id),
                ),
            };
        }
        setOver(overRef.current);
        setDrag({
            type: press.type,
            id: press.id,
            x: e.clientX - dragRef.current.dx,
            y: e.clientY - dragRef.current.dy,
            w: r.width,
        });
        document.body.classList.add("kb-grabbing");
        dragRef.current.raf = requestAnimationFrame(autoScrollTick);
    };

    const endDrag = () => {
        if (dragRef.current?.raf) cancelAnimationFrame(dragRef.current.raf);
        pressRef.current = null;
        dragRef.current = null;
        overRef.current = null;
        setDrag(null);
        setOver(null);
        document.body.classList.remove("kb-grabbing");
    };

    const onMove = (e) => {
        const press = pressRef.current;
        if (press && !dragRef.current) {
            if (Math.hypot(e.clientX - press.startX, e.clientY - press.startY) < DRAG_THRESHOLD)
                return;
            beginDrag(e);
        }
        const d = dragRef.current;
        if (!d) return;
        d.px = e.clientX;
        d.py = e.clientY;
        setDrag((p) => p && { ...p, x: e.clientX - d.dx, y: e.clientY - d.dy });
        updateOver(e.clientX, e.clientY);
    };

    const onUp = () => {
        const d = dragRef.current;
        const ov = overRef.current;
        if (d && ov) {
            if (d.type === "card") {
                const cols = new Map(
                    groups.map((g) => [
                        g.id,
                        (catsByGroup.get(g.id) ?? []).filter((c) => c.id !== d.id),
                    ]),
                );
                const moved = snapshot.categories.find((c) => c.id === d.id);
                const dest = cols.get(ov.groupId);
                if (moved && dest) {
                    dest.splice(Math.min(ov.index, dest.length), 0, moved);
                    const orderedIds = groups.flatMap((g) => cols.get(g.id).map((c) => c.id));
                    moveCategory(d.id, ov.groupId, orderedIds);
                }
            } else {
                const ids = groups.map((g) => g.id).filter((id) => id !== d.id);
                ids.splice(Math.min(ov.index, ids.length), 0, d.id);
                reorderGroups(ids);
            }
        }
        endDrag();
    };

    const onKey = (e) => {
        if (e.key === "Escape" && dragRef.current) endDrag();
    };

    handlersRef.current = { onMove, onUp, onKey, endDrag };

    useEffect(() => {
        const move = (e) => handlersRef.current.onMove(e);
        const up = () => handlersRef.current.onUp();
        const cancel = () => handlersRef.current.endDrag();
        const key = (e) => handlersRef.current.onKey(e);
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
        window.addEventListener("pointercancel", cancel);
        window.addEventListener("keydown", key);
        return () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
            window.removeEventListener("pointercancel", cancel);
            window.removeEventListener("keydown", key);
            handlersRef.current.endDrag();
        };
    }, []);

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

    const renderCard = (c) => (
        <div
            key={c.id}
            data-id={c.id}
            className={`kb-card${drag?.type === "card" && drag.id === c.id ? " kb-card_ghost" : ""}`}
            onPointerDown={(e) => startPress(e, { type: "card", id: c.id, el: e.currentTarget })}
        >
            <CardBody
                c={c}
                count={txCountByCat.get(c.id) ?? 0}
                menu={<RowMenu size="s" items={catMenu(c)} />}
            />
        </div>
    );

    const dragCat =
        drag?.type === "card" ? snapshot.categories.find((c) => c.id === drag.id) : null;
    const dragGroup = drag?.type === "col" ? groups.find((g) => g.id === drag.id) : null;

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
                    variant="filled"
                    size="m"
                    onClick={() =>
                        setDialog({ type: "cat-edit", category: { groupId: groups[0]?.id } })
                    }
                    disabled={groups.length === 0}
                    leftSection={<Plus width={14} height={14} />}
                >
                    New category
                </Button>
            </div>

            <div className={`kb-board${drag ? " kb-board_dragging" : ""}`} ref={boardRef}>
                {shownGroups.map((g) => {
                    const cats = catsByGroup.get(g.id) ?? [];
                    const shown = previewCats(g.id);
                    const isGhost = drag?.type === "col" && drag.id === g.id;
                    return (
                        <div
                            key={g.id}
                            data-gid={g.id}
                            className={`kb-col kb-col_${g.kind}${isGhost ? " kb-col_ghost" : ""}`}
                        >
                            <div
                                className="kb-col__head"
                                onPointerDown={(e) =>
                                    startPress(e, { type: "col", id: g.id, el: e.currentTarget })
                                }
                            >
                                <span className="kb-col__name">{g.name}</span>
                                <Tag theme={g.kind === "income" ? "success" : "danger"}>
                                    {g.kind}
                                </Tag>
                                <span className="kb-col__count">{cats.length}</span>
                                <div style={{ marginLeft: "auto" }}>
                                    <RowMenu size="s" items={groupMenu(g)} />
                                </div>
                            </div>

                            <div className="kb-cards">{shown.map((c) => renderCard(c))}</div>

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

            {drag && (
                <div className="kb-drag-layer" style={{ left: drag.x, top: drag.y, width: drag.w }}>
                    {dragCat && (
                        <div className="kb-card kb-card_clone">
                            <CardBody c={dragCat} count={txCountByCat.get(dragCat.id) ?? 0} />
                        </div>
                    )}
                    {dragGroup && (
                        <div className={`kb-col kb-col_clone kb-col_${dragGroup.kind}`}>
                            <div className="kb-col__head">
                                <span className="kb-col__name">{dragGroup.name}</span>
                                <Tag theme={dragGroup.kind === "income" ? "success" : "danger"}>
                                    {dragGroup.kind}
                                </Tag>
                                <span className="kb-col__count">
                                    {(catsByGroup.get(dragGroup.id) ?? []).length}
                                </span>
                            </div>
                            <div className="kb-cards">
                                {(catsByGroup.get(dragGroup.id) ?? []).map((c) => (
                                    <div key={c.id} className="kb-card">
                                        <CardBody c={c} count={txCountByCat.get(c.id) ?? 0} />
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

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

function CardBody({ c, count, menu }) {
    return (
        <>
            <div className="kb-card__top">
                <span className="kb-card__name">{c.name}</span>
                {c.archived && <Tag theme="warning">arch</Tag>}
                <span className="kb-card__usage" title={`${count} transactions`}>
                    {count}
                </span>
                {menu && <div className="kb-card__menu">{menu}</div>}
            </div>
            {c.keywords && (
                <div className="kb-card__kw">
                    {c.keywords.split("|").filter(Boolean).join(", ")}
                </div>
            )}
        </>
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
