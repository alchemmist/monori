import type { Transaction } from "../types.js";

/** The amount a transaction contributes to reporting-currency totals. */
export function reported(transaction: Pick<Transaction, "amount" | "baseAmount">): number {
    return transaction.baseAmount ?? transaction.amount;
}
