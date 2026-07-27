/** Replace split containers with their categorized parts for derived calculations. */
export function effectiveTransactions(transactions = []) {
    return transactions.flatMap((transaction) => {
        if (!transaction.splits?.length) return transaction;
        return transaction.splits.map((part) => ({
            ...transaction,
            id: `${transaction.id}:${part.id}`,
            parentId: transaction.id,
            splitId: part.id,
            categoryId: part.categoryId,
            amount: part.amount,
            comment: part.comment,
            splits: [],
        }));
    });
}
