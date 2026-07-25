/**
 * The currencies monori knows about.
 *
 * A short curated list, not all of ISO 4217, and every entry has two minor
 * units — which is what lets every amount stay an integer count of them and the
 * currency be a label on top. `server/app/currencies.py` is the same list on
 * the server; a code offered here but rejected there would only ever surface as
 * a 400 in someone's account dialog, so `test_currencies.py` pins them together.
 */
export const CURRENCIES = [
    { code: "RUB", name: "Russian ruble", symbol: "₽" },
    { code: "USD", name: "US dollar", symbol: "$" },
    { code: "EUR", name: "Euro", symbol: "€" },
    { code: "GBP", name: "Pound sterling", symbol: "£" },
    { code: "CHF", name: "Swiss franc", symbol: "CHF" },
    { code: "KZT", name: "Kazakhstani tenge", symbol: "₸" },
    { code: "BYN", name: "Belarusian ruble", symbol: "Br" },
    { code: "GEL", name: "Georgian lari", symbol: "₾" },
    { code: "AMD", name: "Armenian dram", symbol: "֏" },
    { code: "TRY", name: "Turkish lira", symbol: "₺" },
    { code: "AED", name: "UAE dirham", symbol: "AED" },
    { code: "CNY", name: "Chinese yuan", symbol: "¥" },
    { code: "RSD", name: "Serbian dinar", symbol: "RSD" },
];

export const DEFAULT_CURRENCY = "RUB";

const BY_CODE = new Map(CURRENCIES.map((c) => [c.code, c]));

/** " gel " -> "GEL"; anything blank becomes the fallback */
export function normalizeCurrency(code, fallback = DEFAULT_CURRENCY) {
    const normalized = String(code ?? "")
        .trim()
        .toUpperCase();
    return normalized || fallback;
}

/** The symbol printed after an amount; an unknown code prints as itself. */
export function currencySymbol(code) {
    const normalized = normalizeCurrency(code, "");
    return BY_CODE.get(normalized)?.symbol ?? normalized;
}

export function currencyName(code) {
    const normalized = normalizeCurrency(code, "");
    return BY_CODE.get(normalized)?.name ?? normalized;
}

/** Options for a select; an unknown code (older account, imported data) is kept
 * as its own option so editing an account never silently rewrites it. */
export function currencyOptions(current) {
    const options = CURRENCIES.map((c) => ({ value: c.code, label: `${c.code} · ${c.name}` }));
    const code = normalizeCurrency(current, "");
    if (code && !BY_CODE.has(code)) {
        options.unshift({ value: code, label: code });
    }
    return options;
}
