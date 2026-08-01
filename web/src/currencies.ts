/* Cosmetic list for the account form: currency is still just a label — every
 * amount is treated as a single currency until real multi-currency lands. */
export const CURRENCIES = [
    { code: "RUB", name: "Russian ruble" },
    { code: "USD", name: "US dollar" },
    { code: "EUR", name: "Euro" },
    { code: "GBP", name: "Pound sterling" },
    { code: "KZT", name: "Kazakhstani tenge" },
    { code: "BYN", name: "Belarusian ruble" },
    { code: "GEL", name: "Georgian lari" },
    { code: "AMD", name: "Armenian dram" },
    { code: "TRY", name: "Turkish lira" },
    { code: "AED", name: "UAE dirham" },
    { code: "CNY", name: "Chinese yuan" },
    { code: "RSD", name: "Serbian dinar" },
];

export const DEFAULT_CURRENCY = "RUB";

/** Options for a select; an unknown code (older account, imported data) is kept
 * as its own option so editing an account never silently rewrites it. */
export function currencyOptions(current?: string | null) {
    const options = CURRENCIES.map((c) => ({ value: c.code, label: `${c.code} · ${c.name}` }));
    const code = (current ?? "").trim().toUpperCase();
    if (code && !CURRENCIES.some((c) => c.code === code)) {
        options.unshift({ value: code, label: code });
    }
    return options;
}
