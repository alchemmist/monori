import { useState } from "react";
import { SegmentedControl } from "@mantine/core";
import { useStore } from "../store.js";
import AppDialog from "../ui/AppDialog.jsx";
import { FTextInput } from "../ui/fields.jsx";
import Txt from "../ui/Txt.jsx";

export function GroupEditDialog({ group, onClose }) {
    const { createGroup, patchGroup, notify } = useStore();
    const isNew = !group.id;
    const [name, setName] = useState(group.name ?? "");
    const [kind, setKind] = useState(group.kind ?? "expense");
    const [busy, setBusy] = useState(false);

    const apply = async () => {
        if (!name.trim()) return;
        setBusy(true);
        try {
            if (isNew) {
                await createGroup({ name: name.trim(), kind });
            } else {
                await patchGroup(group.id, { name: name.trim(), kind });
            }
            onClose();
        } catch (e) {
            notify({
                title: isNew ? "Failed to create group" : "Failed to update group",
                theme: "danger",
                content: String(e),
            });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title={isNew ? "New group" : `Edit ${group.name}`}
            onClose={onClose}
            applyText={isNew ? "Create" : "Save"}
            onApply={apply}
            applyLoading={busy}
            applyDisabled={!name.trim()}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 14, paddingTop: 4 }}>
                <FTextInput
                    label="Name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoFocus
                />
                <div>
                    <Txt block style={{ fontWeight: 600, marginBottom: 6 }}>
                        Kind
                    </Txt>
                    <SegmentedControl
                        fullWidth
                        value={kind}
                        onChange={setKind}
                        data={[
                            { value: "income", label: "Income" },
                            { value: "expense", label: "Expense" },
                        ]}
                    />
                </div>
                <Txt tone="secondary" caption>
                    Income groups collect money coming in; expense groups collect what you spend.
                    Categories inside inherit this split for auto-categorization.
                </Txt>
            </div>
        </AppDialog>
    );
}

export function GroupDeleteDialog({ group, catCount, onClose }) {
    const { deleteGroup, notify } = useStore();
    const [busy, setBusy] = useState(false);
    const blocked = catCount > 0;

    const apply = async () => {
        setBusy(true);
        try {
            await deleteGroup(group.id);
            onClose();
        } catch (e) {
            notify({ title: "Failed to delete group", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title={`Delete ${group.name}`}
            onClose={onClose}
            applyText="Delete"
            onApply={apply}
            applyLoading={busy}
            applyDisabled={blocked}
            applyDanger
        >
            <Txt block>
                {blocked
                    ? `This group still holds ${catCount} ${
                          catCount === 1 ? "category" : "categories"
                      }. Move or delete them first — drag the cards to another column.`
                    : "This group is empty and will be removed. Nothing else is affected."}
            </Txt>
        </AppDialog>
    );
}
