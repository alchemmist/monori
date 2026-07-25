import { api } from "../api.js";
import { demoSnapshot } from "./demoData.js";

const seedAccountRef = (id) => `monori-demo:${id}`;

function uniqueDemoName(accounts, name) {
    const names = new Set(accounts.map((a) => a.name));
    if (!names.has(name)) return name;
    for (let n = 2; ; n += 1) {
        const candidate = `${name} (Demo ${n})`;
        if (!names.has(candidate)) return candidate;
    }
}

async function allTransactions() {
    const rows = [];
    for (;;) {
        const page = await api.transactions({ limit: 1000, offset: rows.length });
        rows.push(...page.rows);
        if (rows.length >= page.total || page.rows.length === 0) return rows;
    }
}

/**
 * Replay the bundled /demo dataset into the signed-in account through the
 * regular API. Accounts are marked in their bank reference so retries can
 * reuse only accounts created by this flow; transactions use import hashes.
 */
export async function seedDemoData() {
    // Always start from the server's current state. A previous attempt can
    // have created accounts before failing later in the import.
    const snapshot = await api.snapshot({ light: true });
    const accId = new Map();
    const accBySeedRef = new Map(snapshot.accounts.map((a) => [a.bankRef, a]));
    for (const a of demoSnapshot.accounts) {
        const bankRef = seedAccountRef(a.id);
        const props = {
            type: a.type,
            icon: a.icon,
            color: a.color,
            currency: a.currency,
            openingBalance: a.openingBalance,
            openingDate: a.openingDate,
            bankRef,
        };
        const existing = accBySeedRef.get(bankRef);
        if (existing) {
            await api.patchAccount(existing.id, props);
            accId.set(a.id, existing.id);
        } else {
            const name = uniqueDemoName(snapshot.accounts, a.name);
            const id = (await api.createAccount({ name, ...props })).id;
            accId.set(a.id, id);
            snapshot.accounts.push({ id, name, bankRef });
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

    // Transfer pairs do not use import hashes. Match every pair independently
    // so a retry repairs a partial run without duplicating completed transfers.
    let transfers = 0;
    const transferPairs = new Map();
    for (const tx of demoSnapshot.transactions) {
        if (!tx.transferId) continue;
        const pair = transferPairs.get(tx.transferId) ?? {};
        pair[tx.amount < 0 ? "out" : "inn"] = tx;
        transferPairs.set(tx.transferId, pair);
    }
    const existing = await allTransactions();
    for (const { out, inn } of transferPairs.values()) {
        const fromAccountId = accId.get(out.accountId);
        const toAccountId = accId.get(inn.accountId);
        const exists = existing.some(
            (t) =>
                t.transferId &&
                t.accountId === fromAccountId &&
                t.amount === -inn.amount &&
                t.date.slice(0, 10) === out.date &&
                t.comment === (out.comment ?? ""),
        );
        if (!exists) {
            await api.createTransfer({
                fromAccountId,
                toAccountId,
                amount: inn.amount,
                date: `${inn.date}T12:00:00`,
                comment: out.comment ?? "",
            });
            transfers += 1;
        }
    }

    return { imported, skipped, transfers };
}
