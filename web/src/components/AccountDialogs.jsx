import { useMemo, useRef, useState } from "react";
import { Button } from "@mantine/core";
import { TrashBin } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import { parseRub, money } from "../format.js";
import { ACCOUNT_ICONS, ACCOUNT_COLORS, DEFAULT_ACCOUNT_COLOR } from "./accountIcons.js";
import AccountBadge from "./AccountBadge.jsx";
import AppDialog from "../ui/AppDialog.jsx";
import { FSelect, FTextInput } from "../ui/fields.jsx";
import Txt from "../ui/Txt.jsx";

const ACCOUNT_TYPES = [
    { value: "card", label: "Card" },
    { value: "cash", label: "Cash" },
    { value: "savings", label: "Savings" },
    { value: "other", label: "Other" },
];

/** Downscale a picked image to a small square-ish PNG data URL so the snapshot
 * stays lean — the badge only ever renders it at ~30px. */
function fileToIconDataUrl(file, max = 128) {
    return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => {
            URL.revokeObjectURL(url);
            const scale = Math.min(1, max / Math.max(img.width, img.height));
            const w = Math.max(1, Math.round(img.width * scale));
            const h = Math.max(1, Math.round(img.height * scale));
            const canvas = document.createElement("canvas");
            canvas.width = w;
            canvas.height = h;
            canvas.getContext("2d").drawImage(img, 0, 0, w, h);
            resolve(canvas.toDataURL("image/png"));
        };
        img.onerror = reject;
        img.src = url;
    });
}

export function AccountEditDialog({ account, onClose }) {
    const { snapshot, createAccount, patchAccount, notify } = useStore();
    const isNew = !account.id;

    // images already used by other accounts, so a logo can be reused without re-uploading
    const savedImages = useMemo(() => {
        const seen = new Set();
        const out = [];
        for (const a of snapshot.accounts ?? []) {
            if (a.iconImage && !seen.has(a.iconImage)) {
                seen.add(a.iconImage);
                out.push(a.iconImage);
            }
        }
        return out;
    }, [snapshot.accounts]);

    const [name, setName] = useState(account.name ?? "");
    const [type, setType] = useState(account.type ?? "other");
    const [icon, setIcon] = useState(account.icon ?? "wallet");
    const [color, setColor] = useState(account.color ?? DEFAULT_ACCOUNT_COLOR);
    const [image, setImage] = useState(account.iconImage ?? "");
    const [currency, setCurrency] = useState(account.currency ?? "RUB");
    const [opening, setOpening] = useState(
        account.openingBalance ? String(account.openingBalance / 100) : "",
    );
    const [busy, setBusy] = useState(false);
    const fileRef = useRef(null);

    const onPickImage = async (e) => {
        const file = e.target.files?.[0];
        e.target.value = "";
        if (!file) return;
        try {
            setImage(await fileToIconDataUrl(file));
        } catch {
            notify({ title: "Could not read that image", theme: "danger" });
        }
    };

    const apply = async () => {
        if (!name.trim()) return;
        const openingBalance = parseRub(opening);
        if (openingBalance == null) {
            notify({ title: "Opening balance is not a number", theme: "danger" });
            return;
        }
        setBusy(true);
        try {
            const body = {
                name: name.trim(),
                type,
                icon,
                color,
                iconImage: image,
                currency: currency.trim() || "RUB",
                openingBalance,
            };
            if (isNew) await createAccount(body);
            else await patchAccount(account.id, body);
            onClose();
        } catch (e) {
            notify({
                title: isNew ? "Failed to create account" : "Failed to update account",
                theme: "danger",
                content: String(e),
            });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title={isNew ? "New account" : `Edit ${account.name}`}
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
                <FSelect label="Type" value={type} onChange={setType} data={ACCOUNT_TYPES} />
                <div>
                    <div className="appearance-head">
                        <Txt tone="secondary" caption>
                            Appearance
                        </Txt>
                        <AccountBadge account={{ icon, color, iconImage: image }} size={34} />
                    </div>

                    {image ? (
                        <div className="appearance-custom">
                            <Txt tone="secondary" caption>
                                Using a custom image. Icon and color don't apply.
                            </Txt>
                            <Button
                                variant="subtle"
                                size="s"
                                onClick={() => setImage("")}
                                title="Remove custom image"
                                leftSection={<TrashBin width={14} height={14} />}
                            >
                                Remove
                            </Button>
                        </div>
                    ) : (
                        <>
                            <div className="icon-picker">
                                {ACCOUNT_ICONS.map(({ name: iconName, Icon }) => (
                                    <button
                                        key={iconName}
                                        type="button"
                                        className={`icon-picker__item ${icon === iconName ? "icon-picker__item_active" : ""}`}
                                        onClick={() => setIcon(iconName)}
                                        aria-label={iconName}
                                        aria-pressed={icon === iconName}
                                    >
                                        <Icon width={18} height={18} />
                                    </button>
                                ))}
                            </div>
                            <div className="color-picker">
                                {ACCOUNT_COLORS.map((c) => (
                                    <button
                                        key={c}
                                        type="button"
                                        className={`color-picker__item ${color === c ? "color-picker__item_active" : ""}`}
                                        style={{ "--swatch": c }}
                                        onClick={() => setColor(c)}
                                        aria-label={c}
                                        aria-pressed={color === c}
                                    />
                                ))}
                            </div>
                            <div className="image-reuse">
                                <Button
                                    variant="light"
                                    size="s"
                                    onClick={() => fileRef.current?.click()}
                                >
                                    Upload custom image…
                                </Button>
                                {savedImages.map((img) => (
                                    <button
                                        key={img}
                                        type="button"
                                        className="image-reuse__item"
                                        onClick={() => setImage(img)}
                                        title="Reuse this image"
                                    >
                                        <img src={img} alt="" />
                                    </button>
                                ))}
                            </div>
                        </>
                    )}
                    <input
                        ref={fileRef}
                        type="file"
                        accept="image/*"
                        hidden
                        onChange={onPickImage}
                    />
                </div>
                <FTextInput
                    label="Currency"
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                />
                <FTextInput
                    label="Opening balance"
                    value={opening}
                    onChange={(e) => setOpening(e.target.value)}
                    placeholder="0"
                />
                <Txt tone="secondary" caption>
                    The running balance is the opening balance plus every transaction on this
                    account. Currency is a label for now — all amounts are treated as a single
                    currency.
                </Txt>
            </div>
        </AppDialog>
    );
}

export function AccountDeleteDialog({ account, accounts, txCount, onClose }) {
    const { deleteAccount, notify } = useStore();
    const others = accounts.filter((a) => a.id !== account.id);
    const [target, setTarget] = useState(others[0] ? String(others[0].id) : "");
    const [busy, setBusy] = useState(false);

    const apply = async () => {
        if (txCount > 0 && !target) return;
        setBusy(true);
        try {
            await deleteAccount(account.id, target ? +target : undefined);
            onClose();
        } catch (e) {
            notify({ title: "Failed to delete account", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title={`Delete ${account.name}`}
            onClose={onClose}
            applyText="Delete"
            onApply={apply}
            applyLoading={busy}
            applyDisabled={txCount > 0 && !target}
            applyDanger
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <Txt block>
                    {txCount > 0
                        ? `${txCount} transactions belong to this account. Move them where?`
                        : "No transactions belong to this account."}
                </Txt>
                {txCount > 0 && (
                    <FSelect
                        label="Move to"
                        value={target || null}
                        onChange={(v) => setTarget(v ?? "")}
                        data={others.map((a) => ({ value: String(a.id), label: a.name }))}
                    />
                )}
            </div>
        </AppDialog>
    );
}

export function AccountReconcileDialog({ account, balance, onClose }) {
    const { reconcileAccount, notify } = useStore();
    const [actual, setActual] = useState(String(balance / 100));
    const [busy, setBusy] = useState(false);
    const actualKop = parseRub(actual);
    const delta = actualKop == null ? null : actualKop - balance;

    const apply = async () => {
        if (actualKop == null) {
            notify({ title: "Balance is not a number", theme: "danger" });
            return;
        }
        setBusy(true);
        try {
            const res = await reconcileAccount(account.id, actualKop);
            notify({
                title:
                    res.delta === 0
                        ? "Already reconciled"
                        : `Adjustment of ${money(res.delta)} posted`,
                theme: "success",
            });
            onClose();
        } catch (e) {
            notify({ title: "Failed to reconcile", theme: "danger", content: String(e) });
        } finally {
            setBusy(false);
        }
    };

    return (
        <AppDialog
            title={`Reconcile ${account.name}`}
            onClose={onClose}
            applyText="Reconcile"
            onApply={apply}
            applyLoading={busy}
        >
            <div style={{ display: "flex", flexDirection: "column", gap: 12, paddingTop: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <Txt tone="secondary">Computed balance</Txt>
                    <span className="num">{money(balance)}</span>
                </div>
                <FTextInput
                    label="Actual bank balance"
                    value={actual}
                    onChange={(e) => setActual(e.target.value)}
                    autoFocus
                />
                {delta != null && delta !== 0 && (
                    <Txt tone="secondary" caption>
                        An adjustment of {money(delta)} will be posted so the account matches your
                        bank.
                    </Txt>
                )}
            </div>
        </AppDialog>
    );
}
