/**
 * What a transaction contributes to a total.
 *
 * `amount` is whatever currency the money was actually spent in, so two rows
 * from two accounts cannot be added together. `baseAmount` is the same money in
 * the owner's reporting currency, computed on the server at the rate for the
 * transaction's own date — the one field that is comparable across the ledger.
 *
 * Every cross-account sum goes through here. The exceptions are deliberate and
 * few: an account's own balance is in the account's own currency, and so is the
 * amount printed on the transaction row itself.
 */
export function reported(t) {
    return t.baseAmount ?? t.amount;
}
