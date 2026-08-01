import type { Transaction, TransactionSplit } from "../types.js";

export type EffectiveTransaction = Omit<Transaction, "id"> & {
    id: number | string;
    parentId?: number;
    splitId?: number | string;
};

/** Replace split containers with their categorized parts for derived calculations. */
export function splitPartTransaction(
    transaction: Transaction,
    part: TransactionSplit,
): EffectiveTransaction {
    return {
        ...transaction,
        id: `${transaction.id}:${part.id}`,
        parentId: transaction.id,
        splitId: part.id,
        categoryId: part.categoryId,
        amount: part.amount,
        comment: part.comment,
        splits: [],
    };
}

export function effectiveTransactions(transactions: Transaction[] = []): EffectiveTransaction[] {
    return transactions.flatMap((transaction) => {
        if (!transaction.splits?.length) return transaction;
        return transaction.splits.map((part) => splitPartTransaction(transaction, part));
    });
}
