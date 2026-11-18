import { DEFAULT_CURRENCY, normalizeCurrency } from "./currencies.js";
import type { Account, ExchangeRate, Id } from "./types.js";

export function ratesByCode(rates: ExchangeRate[] = []): Map<string, number> {
    const map = new Map(rates.map((rate) => [normalizeCurrency(rate.code), rate.rate]));
    map.set(DEFAULT_CURRENCY, 1);
    return map;
}

export function convertAmount(
    amount: number,
    from: string | undefined,
    to: string,
    rates: ExchangeRate[] | Map<string, number>,
): number {
    const source = normalizeCurrency(from);
    const target = normalizeCurrency(to);
    if (source === target) return amount;
    const table = rates instanceof Map ? rates : ratesByCode(rates);
    const sourceRate = table.get(source);
    const targetRate = table.get(target);
    if (sourceRate == null || targetRate == null || sourceRate <= 0 || targetRate <= 0) {
        throw new Error(`Missing exchange rate for ${sourceRate == null ? source : target}`);
    }
    const converted = Math.round((amount * sourceRate) / targetRate);
    return converted === 0 ? 0 : converted;
}

export function totalInBase(
    accounts: Array<Pick<Account, "id" | "currency" | "archived">>,
    balances: Map<Id, number>,
    base: string,
    rates: ExchangeRate[],
): number {
    const table = ratesByCode(rates);
    return accounts.reduce(
        (total, account) =>
            account.archived
                ? total
                : total +
                  convertAmount(balances.get(account.id) ?? 0, account.currency, base, table),
        0,
    );
}

export function isMixedCurrency(
    accounts: Array<Pick<Account, "currency" | "archived">>,
    base: string,
): boolean {
    const target = normalizeCurrency(base);
    return accounts.some(
        (account) => !account.archived && normalizeCurrency(account.currency) !== target,
    );
}
