/**
 * Decoding for uploaded bank statement files (CSV export).
 * Russian banks ship CSVs in windows-1251 about as often as in UTF-8, so we
 * try strict UTF-8 first and fall back to cp1251 when the bytes don't decode.
 */
import type { ImportRow } from "./types.js";

export function decodeStatementBytes(buffer: AllowSharedBufferSource) {
    try {
        return new TextDecoder("utf-8", { fatal: true }).decode(buffer);
    } catch {
        return new TextDecoder("windows-1251").decode(buffer);
    }
}

// generous for statements (~100 bytes/row → ~50k rows) while keeping an
// accidental wrong-file pick from buffering hundreds of megabytes
export const MAX_STATEMENT_FILE_BYTES = 5_000_000;

export async function readStatementFile(file: {
    size: number;
    arrayBuffer?: () => Promise<AllowSharedBufferSource>;
}) {
    if (!file.size) throw new Error("the file is empty");
    if (file.size > MAX_STATEMENT_FILE_BYTES) {
        const mb = Math.round(MAX_STATEMENT_FILE_BYTES / 1_000_000);
        throw new Error(`the file is larger than ${mb} MB — not a statement export?`);
    }
    if (!file.arrayBuffer) throw new Error("the file cannot be read");
    return decodeStatementBytes(await file.arrayBuffer());
}

/** True when a stored account tail and a statement tail point at the same
 * card: either is a suffix of the other, so a 4-digit statement tail still
 * matches a longer stored tail like '553691...2947'. */
export function tailMatches(storedTail: string, statementTail: string) {
    if (!storedTail || !statementTail) return false;
    return storedTail.endsWith(statementTail) || statementTail.endsWith(storedTail);
}

/** Distinct card tails found in parsed statement rows ('*8181' -> '8181'). */
export function statementTails(
    rows: Array<Partial<Pick<ImportRow, "card">>> | undefined,
): string[] {
    const tails = new Set<string>();
    for (const r of rows ?? []) {
        const t = String(r.card ?? "")
            .replace(/\D/g, "")
            .slice(-4);
        if (t) tails.add(t);
    }
    return [...tails];
}
