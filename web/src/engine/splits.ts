import type { Transaction, TransactionSplit } from "../types.js";
import { roundHalfEven } from "../money.js";

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
    const parentBaseAmount = transaction.baseAmount ?? transaction.amount;
    const baseAmount =
        transaction.amount === 0
            ? 0
            : roundHalfEven((parentBaseAmount * part.amount) / transaction.amount);
    const parentAccountAmount = transaction.accountAmount ?? transaction.amount;
    const accountAmount =
        transaction.amount === 0
            ? 0
            : roundHalfEven((parentAccountAmount * part.amount) / transaction.amount);
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
        let allocated = 0;
        let accountAllocated = 0;
        const splits = transaction.splits;
        return splits.map((part, index) => {
            const row = splitPartTransaction(transaction, part);
            if (index === splits.length - 1) {
                row.baseAmount = (transaction.baseAmount ?? transaction.amount) - allocated;
                row.accountAmount =
                    (transaction.accountAmount ?? transaction.amount) - accountAllocated;
            }
            allocated += row.baseAmount ?? 0;
            accountAllocated += row.accountAmount ?? 0;
            return row;
        });
    });
}
