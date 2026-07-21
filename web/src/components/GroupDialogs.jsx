import { useState } from "react";
import { Dialog, TextInput, SegmentedRadioGroup, Text } from "@gravity-ui/uikit";
import { useStore } from "../store.js";

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
        <Dialog open onClose={onClose} size="s">
            <Dialog.Header caption={isNew ? "New group" : `Edit ${group.name}`} />
            <Dialog.Body>
                <div style={{ display: "flex", flexDirection: "column", gap: 14, paddingTop: 4 }}>
                    <TextInput label="Name" value={name} onUpdate={setName} autoFocus />
                    <div>
                        <Text variant="subheader-1" style={{ display: "block", marginBottom: 6 }}>
                            Kind
                        </Text>
                        <SegmentedRadioGroup value={kind} onUpdate={setKind} width="max">
                            <SegmentedRadioGroup.Option value="income">
                                Income
                            </SegmentedRadioGroup.Option>
                            <SegmentedRadioGroup.Option value="expense">
                                Expense
                            </SegmentedRadioGroup.Option>
                        </SegmentedRadioGroup>
                    </div>
                    <Text color="secondary" variant="caption-2">
                        Income groups collect money coming in; expense groups collect what you
                        spend. Categories inside inherit this split for auto-categorization.
                    </Text>
                </div>
            </Dialog.Body>
            <Dialog.Footer
                textButtonApply={isNew ? "Create" : "Save"}
                textButtonCancel="Cancel"
                onClickButtonApply={apply}
                onClickButtonCancel={onClose}
                propsButtonApply={{ loading: busy, disabled: !name.trim() }}
            />
        </Dialog>
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
        <Dialog open onClose={onClose} size="s">
            <Dialog.Header caption={`Delete ${group.name}`} />
            <Dialog.Body>
                <Text>
                    {blocked
                        ? `This group still holds ${catCount} ${
                              catCount === 1 ? "category" : "categories"
                          }. Move or delete them first — drag the cards to another column.`
                        : "This group is empty and will be removed. Nothing else is affected."}
                </Text>
            </Dialog.Body>
            <Dialog.Footer
                textButtonApply="Delete"
                textButtonCancel="Cancel"
                onClickButtonApply={apply}
                onClickButtonCancel={onClose}
                propsButtonApply={{ view: "outlined-danger", loading: busy, disabled: blocked }}
            />
        </Dialog>
    );
}
