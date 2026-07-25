import { describe, expect, it } from "vitest";
import { MAX_STATEMENT_FILE_BYTES, decodeStatementBytes, readStatementFile } from "./importFile.js";

describe("decodeStatementBytes", () => {
    it("decodes valid UTF-8 as UTF-8", () => {
        const bytes = new TextEncoder().encode("Дата операции;Метро;-20,00");
        expect(decodeStatementBytes(bytes)).toBe("Дата операции;Метро;-20,00");
    });

    it("falls back to windows-1251 when the bytes are not UTF-8", () => {
        // "Метро" in cp1251: crooked as UTF-8, valid as windows-1251
        const cp1251 = new Uint8Array([0xcc, 0xe5, 0xf2, 0xf0, 0xee]);
        expect(decodeStatementBytes(cp1251)).toBe("Метро");
    });

    it("keeps plain ASCII intact either way", () => {
        const ascii = new TextEncoder().encode("05.07.2026;OK;-20.00");
        expect(decodeStatementBytes(ascii)).toBe("05.07.2026;OK;-20.00");
    });
});

describe("readStatementFile", () => {
    const fakeFile = (bytes) => ({
        size: bytes.byteLength,
        arrayBuffer: async () => bytes,
    });

    it("reads and decodes a normal file", async () => {
        const bytes = new TextEncoder().encode("05.07.2026;OK;-20.00");
        expect(await readStatementFile(fakeFile(bytes))).toBe("05.07.2026;OK;-20.00");
    });

    it("rejects empty and oversized files without reading them", async () => {
        await expect(readStatementFile({ size: 0 })).rejects.toThrow(/empty/);
        await expect(readStatementFile({ size: MAX_STATEMENT_FILE_BYTES + 1 })).rejects.toThrow(
            /larger than/,
        );
    });
});
