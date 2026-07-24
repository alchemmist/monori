import { describe, expect, it } from "vitest";
import { decodeStatementBytes, statementTails } from "./importFile.js";

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
