/**
 * Decoding for uploaded bank statement files (CSV export).
 * Russian banks ship CSVs in windows-1251 about as often as in UTF-8, so we
 * try strict UTF-8 first and fall back to cp1251 when the bytes don't decode.
 */
export function decodeStatementBytes(buffer) {
    try {
        return new TextDecoder("utf-8", { fatal: true }).decode(buffer);
    } catch {
        return new TextDecoder("windows-1251").decode(buffer);
    }
}

export async function readStatementFile(file) {
    return decodeStatementBytes(await file.arrayBuffer());
}
