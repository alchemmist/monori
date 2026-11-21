import type { Transaction, TransactionSplit } from "../types.js";
import { roundRatio } from "../money.js";

export type EffectiveTransaction = Omit<Transaction, "id"> & {
    id: number | string;
    parentId?: number;
    splitId?: number | string;
};

/** Replace split containers with their categorized parts for derived calculations. */
export function splitPartTransaction(
    transaction: Transaction,
    part: TransactionSplit,
    amountBefore?: number,
): EffectiveTransaction {
    const siblings = transaction.splits ?? [];
    const before =
        amountBefore ??
        siblings
            .slice(
                0,
                Math.max(
                    0,
                    siblings.findIndex((sibling) => sibling.id === part.id),
                ),
            )
            .reduce((sum, sibling) => sum + sibling.amount, 0);
    const after = before + part.amount;
    const parentBaseAmount = transaction.baseAmount ?? transaction.amount;
    const baseAmount =
        roundRatio(BigInt(parentBaseAmount) * BigInt(after), BigInt(transaction.amount)) -
        roundRatio(BigInt(parentBaseAmount) * BigInt(before), BigInt(transaction.amount));
    const parentAccountAmount = transaction.accountAmount ?? transaction.amount;
    const accountAmount =
        roundRatio(BigInt(parentAccountAmount) * BigInt(after), BigInt(transaction.amount)) -
        roundRatio(BigInt(parentAccountAmount) * BigInt(before), BigInt(transaction.amount));
    return {
        ...transaction,
        id: `${transaction.id}:${part.id}`,
        parentId: transaction.id,
        splitId: part.id,
        categoryId: part.categoryId,
        amount: part.amount,
        baseAmount,
        accountAmount,
        comment: part.comment,
        splits: [],
    };
}

export function effectiveTransactions(transactions: Transaction[] = []): EffectiveTransaction[] {
    return transactions.flatMap((transaction) => {
        if (transaction.splits == null || transaction.splits.length === 0) return transaction;
        let cumulative = 0;
        return transaction.splits.map((part) => {
            const row = splitPartTransaction(transaction, part, cumulative);
            cumulative += part.amount;
            return row;
        });
    });
}
