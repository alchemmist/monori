import { api } from "../api.js";
import { demoSnapshot } from "./demoData.js";

/**
 * Replay the bundled /demo dataset into the signed-in account through the
 * regular API: accounts, groups and categories are matched by name (so a
 * second run reuses them), transactions go through the import endpoint whose
 * hash dedup makes re-runs skip everything already there.
 */
export async function seedDemoData(snapshot) {
    const accId = new Map();
    const accByName = new Map(snapshot.accounts.map((a) => [a.name, a]));
    for (const a of demoSnapshot.accounts) {
        const props = {
            type: a.type,
            icon: a.icon,
            color: a.color,
            currency: a.currency,
            openingBalance: a.openingBalance,
            openingDate: a.openingDate,
        };
        const existing = accByName.get(a.name);
        if (existing) {
            await api.patchAccount(existing.id, props);
            accId.set(a.id, existing.id);
        } else {
            accId.set(a.id, (await api.createAccount({ name: a.name, ...props })).id);
        }
    }

    const grpId = new Map();
    const grpByName = new Map(snapshot.groups.map((g) => [g.name, g.id]));
    for (const g of demoSnapshot.groups) {
        grpId.set(
            g.id,
            grpByName.get(g.name) ?? (await api.createGroup({ name: g.name, kind: g.kind })).id,
        );
    }

    const catId = new Map();
    const catByName = new Map(snapshot.categories.map((c) => [c.name, c.id]));
    for (const c of demoSnapshot.categories) {
        catId.set(
            c.id,
            catByName.get(c.name) ??
                (
                    await api.createCategory({
                        name: c.name,
                        groupId: grpId.get(c.groupId),
                        keywords: c.keywords ?? "",
                    })
                ).id,
        );
    }

    await api.bulkBudgets(
        demoSnapshot.budgets.map((b) => ({
            categoryId: catId.get(b.categoryId),
            year: b.year,
            month: b.month,
            amount: b.amount,
        })),
    );

    let imported = 0;
    let skipped = 0;
    for (const a of demoSnapshot.accounts) {
        const rows = demoSnapshot.transactions
            .filter((t) => t.accountId === a.id && t.transferId == null)
            .map((t) => ({
                date: `${t.date}T12:00:00`,
                amount: t.amount,
                description: t.description,
                bank_category: t.bankCategory ?? "",
                mcc: t.mcc ?? "",
                categoryId: t.categoryId ? catId.get(t.categoryId) : null,
            }));
        const res = await api.importCommit(rows, accId.get(a.id));
        imported += res.imported ?? 0;
        skipped += res.skipped ?? 0;
    }

    // transfer pairs are not deduped by the import hash, so only seed them on
    // a run that actually imported something new
    let transfers = 0;
    if (imported > 0) {
        const txById = new Map(demoSnapshot.transactions.map((t) => [t.id, t]));
        for (const tr of demoSnapshot.transfers) {
            const inn = txById.get(tr.inTxId);
            const out = txById.get(tr.outTxId);
            await api.createTransfer({
                fromAccountId: accId.get(out.accountId),
                toAccountId: accId.get(inn.accountId),
                amount: inn.amount,
                date: `${inn.date}T12:00:00`,
                comment: tr.note ?? "",
            });
            transfers += 1;
        }
    }

    return { imported, skipped, transfers };
}
