/**
 * The little bit of currency conversion the client has to do for itself.
 *
 * Transactions arrive with `baseAmount` already computed by the server at the
 * rate for their own date, so nothing here touches them. What is left over is
 * the money that has no transaction behind it — an account's opening balance,
 * and therefore its running balance — which has to be converted at today's rate
 * to be added to anything else.
 *
 * Rates are quoted in rubles per unit, so a conversion is `amount * from / to`.
 */
import { DEFAULT_CURRENCY, normalizeCurrency } from "./currencies.js";

/** The snapshot's rate list as a lookup; the pivot is always exactly one. */
export function ratesByCode(rates = []) {
    const map = new Map(rates.map((r) => [normalizeCurrency(r.code), r.rate]));
    map.set(DEFAULT_CURRENCY, 1);
    return map;
}

/** `amount` minor units of `from`, expressed in `to`. An unquoted currency is
 * carried across at face value — the same call the server makes — rather than
 * dropping the money out of the total entirely. */
export function convertAmount(amount, from, to, rates) {
    const src = normalizeCurrency(from);
    const dst = normalizeCurrency(to);
    if (src === dst) return amount;
    const table = rates instanceof Map ? rates : ratesByCode(rates);
    const srcRate = table.get(src);
    const dstRate = table.get(dst);
    if (!srcRate || !dstRate) return amount;
    return Math.round((amount * srcRate) / dstRate);
}

/**
 * Every account's balance added up in the reporting currency.
 *
 * `balances` is what `accountBalances()` returns: each account's own money in
 * its own currency. Archived accounts are left out, matching the accounts page.
 */
export function totalInBase(accounts, balances, base, rates) {
    const table = ratesByCode(rates);
    let total = 0;
    for (const a of accounts) {
        if (a.archived) continue;
        total += convertAmount(balances.get(a.id) ?? 0, a.currency, base, table);
    }
    return total;
}

/** True when the accounts are not all held in the reporting currency — the only
 * case where showing a converted total tells the reader something. */
export function isMixedCurrency(accounts, base) {
    const target = normalizeCurrency(base);
    return accounts.some((a) => !a.archived && normalizeCurrency(a.currency) !== target);
}
