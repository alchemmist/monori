import { DEFAULT_CURRENCY, currencySymbol } from "./currencies.js";

export const MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];
export const MONTHS_SHORT = MONTHS.map((m) => m.slice(0, 3));

const nf0 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** kopecks -> "12 345" (rounded rubles) */
export function rub(kop) {
    return nf0.format(Math.round(kop / 100));
}

/** kopecks -> "12 345.67" */
export function rubExact(kop) {
    return nf2.format(kop / 100);
}

/** minor units + a currency -> "12 345 ₽"; the code defaults to the reporting
 * currency, which is what an aggregate is always expressed in */
export function money(kop, currency = DEFAULT_CURRENCY) {
    return `${rub(kop)} ${currencySymbol(currency)}`;
}

/** compact: 1234500 kop -> "12.3k", for chart axes */
export function moneyCompact(kop) {
    const r = kop / 100;
    const abs = Math.abs(r);
    if (abs >= 1_000_000) return `${(r / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${(r / 1_000).toFixed(0)}k`;
    return `${Math.round(r)}`;
}

/** typed text -> "12 345,5", grouped as you type: keeps a trailing separator
 * and an empty fraction so the field never fights the person filling it in */
export function groupAmount(input) {
    const s = String(input ?? "").replace(/[^\d.,-]/g, "");
    const sign = s.startsWith("-") ? "-" : "";
    const [, int, sep, frac] = (sign ? s.slice(1) : s).match(/^(\d*)([.,]?)(\d*)/);
    const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
    return `${sign}${grouped}${sep}${frac.slice(0, 2)}`;
}

/** kopecks -> the same text a person would type into an amount field */
export function amountInput(kop) {
    if (kop == null || kop === 0) return "";
    return groupAmount(String(kop / 100).replace(".", ","));
}

/** "12 345,50" or "12345.5" -> kopecks (integer), null if invalid */
export function parseRub(input) {
    const s = String(input).trim().replace(/\s| /g, "").replace(",", ".");
    if (!s) return 0;
    const v = Number(s);
    if (!Number.isFinite(v)) return null;
    return Math.round(v * 100);
}

export function fmtDate(iso) {
    return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;
}
