import { api } from "../api.js";
import { demoSnapshot } from "./demoData.js";
import type { Account, Id, Transaction, TransactionPage } from "../types.js";

const seedAccountRef = (id: Id) => `monori-demo:${id}`;

function uniqueDemoName(accounts: Array<Pick<Account, "name">>, name: string) {
    const names = new Set(accounts.map((a) => a.name));
    if (!names.has(name)) return name;
    for (let n = 2; ; n += 1) {
        const candidate = `${name} (Demo ${n})`;
        if (!names.has(candidate)) return candidate;
    }
}

async function allPages(fetchPage: (offset: number) => Promise<TransactionPage>) {
    const rows: Transaction[] = [];
    for (;;) {
        const page = await fetchPage(rows.length);
        rows.push(...page.rows);
        if (rows.length >= page.total || page.rows.length === 0) return rows;
    }
}

async function allTransactions() {
    const [visible, hidden] = await Promise.all([
        allPages((offset) => api.transactions({ limit: 1000, offset })),
        allPages((offset) => api.hiddenTx(offset)),
    ]);
    return [...visible, ...hidden];
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
    const accId = new Map<Id, Id>();
    const accBySeedRef = new Map(snapshot.accounts.map((a) => [a.bankRef, a]));
    for (const a of demoSnapshot.accounts) {
        const bankRef = seedAccountRef(a.id);
        const props = {
            type: a.type,
            icon: a.icon,
            color: a.color,
            currency: a.currency,
            ...(a.openingBalance === undefined ? {} : { openingBalance: a.openingBalance }),
            ...(a.openingDate === undefined ? {} : { openingDate: a.openingDate }),
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
            snapshot.accounts.push({ ...a, id, name, bankRef });
        }
    }

    const grpId = new Map<Id, Id>();
    const grpByName = new Map(snapshot.groups.map((g) => [g.name, g.id]));
    for (const g of demoSnapshot.groups) {
        grpId.set(
            g.id,
            grpByName.get(g.name) ?? (await api.createGroup({ name: g.name, kind: g.kind })).id,
        );
    }

    const catId = new Map<Id, Id>();
    const catByName = new Map(snapshot.categories.map((c) => [c.name, c.id]));
    for (const c of demoSnapshot.categories) {
        catId.set(
            c.id,
            catByName.get(c.name) ??
                (
                    await api.createCategory({
                        name: c.name,
                        groupId: grpId.get(c.groupId) ?? 0,
                        keywords: c.keywords,
                    })
                ).id,
        );
    }

    await api.bulkBudgets(
        demoSnapshot.budgets.map((b) => ({
            categoryId: catId.get(b.categoryId) ?? 0,
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
                bankCategory: t.bankCategory,
                mcc: t.mcc ?? "",
                categoryId: t.categoryId == null ? null : (catId.get(t.categoryId) ?? null),
                accountId: accId.get(a.id) ?? null,
            }));
        const res = await api.importCommit(rows, accId.get(a.id) ?? null);
        imported += res.inserted ?? 0;
        skipped += res.skipped ?? 0;
    }

    // Transfer pairs do not use import hashes. Match every pair independently
    // so a retry repairs a partial run without duplicating completed transfers.
    let transfers = 0;
    const transferPairs = new Map<string, { out?: Transaction; inn?: Transaction }>();
    for (const tx of demoSnapshot.transactions) {
        if (tx.transferId == null || tx.transferId === "") continue;
        const pair = transferPairs.get(tx.transferId) ?? {};
        pair[tx.amount < 0 ? "out" : "inn"] = tx;
        transferPairs.set(tx.transferId, pair);
    }
    const existing = await allTransactions();
    for (const { out, inn } of transferPairs.values()) {
        if (out == null || inn == null) continue;
        const fromAccountId = accId.get(out.accountId);
        const toAccountId = accId.get(inn.accountId);
        if (fromAccountId == null || toAccountId == null) continue;
        const exists = existing.some((t) => {
            if (!(
                t.transferId != null &&
                t.transferId !== "" &&
                t.accountId === fromAccountId &&
                t.amount === -inn.amount &&
                t.date.slice(0, 10) === out.date &&
                t.comment === out.comment
            ))
                return false;
            return existing.some(
                (other) =>
                    other.transferId === t.transferId &&
                    other.accountId === toAccountId &&
                    other.amount === inn.amount,
            );
        });
        if (!exists) {
            await api.createTransfer({
                fromAccountId,
                toAccountId,
                amount: inn.amount,
                date: `${inn.date}T12:00:00`,
                comment: out.comment,
            });
            transfers += 1;
        }
    }

    return { imported, skipped, transfers };
}
