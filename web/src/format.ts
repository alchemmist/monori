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

/** Treat a sub-ruble amount as zero everywhere in the frontend. */
export function normalizeKop(kop: number): number;
export function normalizeKop(kop: null): null;
export function normalizeKop(kop: number | null): number | null;
export function normalizeKop(kop: number | null): number | null {
    return kop != null && Number.isFinite(kop) && Math.abs(kop) < 100 ? 0 : kop;
}

/** kopecks -> "12 345" (rounded rubles) */
export function rub(kop: number): string {
    return nf0.format(Math.round((normalizeKop(kop) ?? 0) / 100));
}

/** kopecks -> "12 345.67" */
export function rubExact(kop: number): string {
    return nf2.format((normalizeKop(kop) ?? 0) / 100);
}

/** kopecks -> "12 345 ₽" */
export function money(kop: number): string {
    return `${rub(kop)} ₽`;
}

/** compact: 1234500 kop -> "12.3k", for chart axes */
export function moneyCompact(kop: number): string {
    const r = (normalizeKop(kop) ?? 0) / 100;
    const abs = Math.abs(r);
    if (abs >= 1_000_000) return `${(r / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${(r / 1_000).toFixed(0)}k`;
    return `${Math.round(r)}`;
}

/** typed text -> "12 345,5", grouped as you type: keeps a trailing separator
 * and an empty fraction so the field never fights the person filling it in */
export function groupAmount(input: string | number | null | undefined): string {
    const s = String(input ?? "").replace(/[^\d.,-]/g, "");
    const sign = s.startsWith("-") ? "-" : "";
    const [, int = "", sep = "", frac = ""] =
        (sign ? s.slice(1) : s).match(/^(\d*)([.,]?)(\d*)/) ?? [];
    const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
    return `${sign}${grouped}${sep}${frac.slice(0, 2)}`;
}

/** kopecks -> the same text a person would type into an amount field */
export function amountInput(kop: number | null): string {
    const normalized = normalizeKop(kop);
    if (normalized == null || normalized === 0) return "";
    return groupAmount(String(normalized / 100).replace(".", ","));
}

/** "12 345,50" or "12345.5" -> kopecks (integer), null if invalid */
export function parseRub(input: unknown): number | null {
    const s = String(input).trim().replace(/\s| /g, "").replace(",", ".");
    if (!s) return 0;
    const v = Number(s);
    if (!Number.isFinite(v)) return null;
    return normalizeKop(Math.round(v * 100));
}

export function fmtDate(iso: string): string {
    return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;
}
