import { describe, expect, it } from "vitest";
import {
    MAX_STATEMENT_FILE_BYTES,
    decodeStatementBytes,
    readStatementFile,
    statementTails,
    tailMatches,
} from "./importFile.js";

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
    const fakeFile = (bytes: AllowSharedBufferSource) => ({
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

    it("accepts a file exactly at the stated size limit", async () => {
        const file = {
            size: MAX_STATEMENT_FILE_BYTES,
            arrayBuffer: async () => new TextEncoder().encode("statement").buffer,
        };
        await expect(readStatementFile(file)).resolves.toBe("statement");
    });

    it("reports the configured limit in megabytes", async () => {
        await expect(readStatementFile({ size: MAX_STATEMENT_FILE_BYTES + 1 })).rejects.toThrow(
            "5 MB",
        );
    });
});

describe("tailMatches", () => {
    it("matches equal tails and mutual suffixes", () => {
        expect(tailMatches("8181", "8181")).toBe(true);
        expect(tailMatches("5536912947", "2947")).toBe(true);
        expect(tailMatches("47", "2947")).toBe(true);
    });

    it("rejects different or empty tails", () => {
        expect(tailMatches("8181", "2947")).toBe(false);
        expect(tailMatches("", "2947")).toBe(false);
        expect(tailMatches("8181", "")).toBe(false);
    });
});

describe("statementTails", () => {
    it("collects distinct digit tails from masked card numbers", () => {
        const rows = [
            { card: "*8181" },
            { card: "*8181" },
            { card: "553691******2947" },
            { card: "" },
            {},
        ];
        expect(statementTails(rows)).toEqual(["8181", "2947"]);
    });

    it("returns empty for missing rows", () => {
        expect(statementTails(undefined)).toEqual([]);
    });
});
