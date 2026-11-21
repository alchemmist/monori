import { DEFAULT_CURRENCY, normalizeCurrency } from "./currencies.js";
import type { Account, ExchangeRate, Id } from "./types.js";

export function ratesByCode(rates: ExchangeRate[] = []): Map<string, number> {
    const map = new Map(rates.map((rate) => [normalizeCurrency(rate.code), rate.rate]));
    map.set(DEFAULT_CURRENCY, 1);
    return map;
}

/** Round an exact ratio to the nearest even minor unit. */
export function roundRatio(numerator: bigint, denominator: bigint): number {
    const negative = numerator < 0n !== denominator < 0n;
    const dividend = numerator < 0n ? -numerator : numerator;
    const divisor = denominator < 0n ? -denominator : denominator;
    let rounded = dividend / divisor;
    const twiceRemainder = (dividend % divisor) * 2n;
    if (twiceRemainder > divisor || (twiceRemainder === divisor && rounded % 2n === 1n)) {
        rounded += 1n;
    }
    return negative && rounded !== 0n ? -Number(rounded) : Number(rounded);
}

function decimalRatio(value: number): [bigint, bigint] {
    const text = value.toString();
    const exponentAt = text.indexOf("e");
    const exponent = exponentAt < 0 ? 0 : Number(text.slice(exponentAt + 1));
    const coefficient = exponentAt < 0 ? text : text.slice(0, exponentAt);
    const dot = coefficient.indexOf(".");
    const fractionDigits = dot < 0 ? 0 : coefficient.length - dot - 1;
    const digits = BigInt(coefficient.replace(".", ""));
    const power = exponent - fractionDigits;
    return power >= 0 ? [digits * 10n ** BigInt(power), 1n] : [digits, 10n ** BigInt(-power)];
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
    if (
        sourceRate == null ||
        targetRate == null ||
        sourceRate <= 0 ||
        targetRate <= 0 ||
        !Number.isFinite(sourceRate) ||
        !Number.isFinite(targetRate)
    ) {
        throw new Error(`Missing exchange rate for ${sourceRate == null ? source : target}`);
    }
    const [sourceNumerator, sourceDenominator] = decimalRatio(sourceRate);
    const [targetNumerator, targetDenominator] = decimalRatio(targetRate);
    const numerator = BigInt(amount) * sourceNumerator * targetDenominator;
    const denominator = sourceDenominator * targetNumerator;
    return roundRatio(numerator, denominator);
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
