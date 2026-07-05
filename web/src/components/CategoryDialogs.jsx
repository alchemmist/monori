import { useState } from "react";
import { Dialog, TextInput, Select, Text } from "@gravity-ui/uikit";
import { useStore } from "../store.js";

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
        await patchCategory(category.id, { name: name.trim(), groupId: +groupId, keywords });
      }
      onClose();
    } catch (e) {
      notify({ title: isNew ? "Failed to create category" : "Failed to update category", theme: "danger", content: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onClose={onClose} size="s">
      <Dialog.Header caption={isNew ? "New category" : `Edit ${category.name}`} />
      <Dialog.Body>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
          <TextInput label="Name" value={name} onUpdate={setName} autoFocus />
          <Select
            label="Group"
            value={[groupId]}
            onUpdate={(v) => setGroupId(v[0])}
            options={groups.map((g) => ({ value: String(g.id), content: g.name }))}
            width="max"
          />
          <TextInput
            label="Keywords"
            value={keywords}
            onUpdate={setKeywords}
            placeholder="Substring|Another substring"
          />
          <Text color="secondary" variant="caption-2">
            Keywords are matched against transaction descriptions during import, separated by |.
            First matching category wins.
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
    <Dialog open onClose={onClose} size="s">
      <Dialog.Header caption={`Delete ${category.name}`} />
      <Dialog.Body>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
          <Text>
            {txCount > 0
              ? `${txCount} transactions use this category. Where should they go?`
              : "No transactions use this category. Its budget history will be removed."}
          </Text>
          {txCount > 0 && (
            <Select
              label="Move to"
              value={target ? [target] : []}
              onUpdate={(v) => setTarget(v[0] ?? "")}
              options={[
                { value: "", content: "Leave uncategorized" },
                ...others.map((c) => ({ value: String(c.id), content: c.name })),
              ]}
              width="max"
            />
          )}
          <Text color="secondary" variant="caption-2">
            Nothing else is affected: other categories, budgets and years stay exactly as they are.
          </Text>
        </div>
      </Dialog.Body>
      <Dialog.Footer
        textButtonApply="Delete"
        textButtonCancel="Cancel"
        onClickButtonApply={apply}
        onClickButtonCancel={onClose}
        propsButtonApply={{ view: "outlined-danger", loading: busy }}
      />
    </Dialog>
  );
}
