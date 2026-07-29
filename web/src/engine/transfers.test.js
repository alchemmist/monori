import { describe, it, expect } from "vitest";
import { isTransfer, mergeTransferRows, transferDates } from "./transfers.js";

const tx = (id, amount, accountId, transferId = null, date = "2026-03-10") => ({
    id,
    date: `${date}T12:00:00`,
    amount,
    description: "Transfer",
    bankCategory: "",
    categoryId: null,
    accountId,
    transferId,
    comment: "",
});

describe("isTransfer", () => {
    it("is true only for a row that carries a transfer id", () => {
        expect(isTransfer(tx(1, -100, 1, "abc"))).toBe(true);
        expect(isTransfer(tx(1, -100, 1))).toBe(false);
        expect(isTransfer({ ...tx(1, -100, 1), transferId: undefined })).toBe(false);
    });
});

describe("mergeTransferRows", () => {
    it("leaves ordinary rows alone", () => {
        const rows = [tx(1, -100, 1), tx(2, 200, 1)];
        expect(mergeTransferRows(rows).map((i) => [i.kind, i.tx.id])).toEqual([
            ["tx", 1],
            ["tx", 2],
        ]);
    });

    it("collapses the two legs into one item at the first leg's position", () => {
        const rows = [tx(1, -100, 1), tx(2, -500, 1, "x"), tx(3, 500, 2, "x"), tx(4, -20, 1)];
        const items = mergeTransferRows(rows);
        expect(items.map((i) => i.kind)).toEqual(["tx", "transfer", "tx"]);
        expect(items[1].out.id).toBe(2);
        expect(items[1].in.id).toBe(3);
        expect(items[1].amount).toBe(500);
    });

    it("sorts the legs by sign, not by the order they arrive in", () => {
        const items = mergeTransferRows([tx(3, 500, 2, "x"), tx(2, -500, 1, "x")]);
        expect([items[0].out.id, items[0].in.id]).toEqual([2, 3]);
    });

    it("still merges when a filter hides one leg, using the full ledger", () => {
        const all = [tx(2, -500, 1, "x"), tx(3, 500, 2, "x")];
        const visible = [all[0]]; // filtered to account 1
        const items = mergeTransferRows(visible, all);
        expect(items).toHaveLength(1);
        expect(items[0].kind).toBe("transfer");
        expect(items[0].in.accountId).toBe(2);
    });

    it("keeps a leg whose partner has not loaded yet as an ordinary row", () => {
        const items = mergeTransferRows([tx(2, -500, 1, "x")]);
        expect(items).toEqual([{ kind: "tx", key: "t2", tx: expect.objectContaining({ id: 2 }) }]);
    });

    it("emits both legs under an expanded transfer", () => {
        const rows = [tx(2, -500, 1, "x"), tx(3, 500, 2, "x")];
        const items = mergeTransferRows(rows, rows, new Set(["x"]));
        expect(items.map((i) => i.kind)).toEqual(["transfer", "leg", "leg"]);
        expect(items.slice(1).map((i) => i.tx.id)).toEqual([2, 3]);
    });

    it("gives every item a stable unique key", () => {
        const rows = [tx(1, -100, 1), tx(2, -500, 1, "x"), tx(3, 500, 2, "x")];
        const keys = mergeTransferRows(rows, rows, new Set(["x"])).map((i) => i.key);
        expect(new Set(keys).size).toBe(keys.length);
    });

    it("handles several transfers without crossing their legs", () => {
        const rows = [
            tx(1, -500, 1, "x"),
            tx(2, -700, 1, "y"),
            tx(3, 500, 2, "x"),
            tx(4, 700, 3, "y"),
        ];
        const items = mergeTransferRows(rows);
        expect(items.map((i) => i.transferId)).toEqual(["x", "y"]);
        expect(items.map((i) => i.amount)).toEqual([500, 700]);
    });

    it("does not merge a malformed group of three legs", () => {
        const rows = [tx(1, -500, 1, "x"), tx(2, 500, 2, "x"), tx(3, 500, 3, "x")];
        expect(mergeTransferRows(rows).map((i) => i.kind)).toEqual(["tx", "tx", "tx"]);
    });
});

describe("transferDates", () => {
    const item = (outDate, inDate) => ({
        out: { date: outDate },
        in: { date: inDate },
    });

    it("reports the outgoing leg's full timestamp as the row date", () => {
        const d = transferDates(item("2026-03-10T09:30:00", "2026-03-11T21:00:00"));
        expect(d.date).toBe("2026-03-10T09:30:00");
    });

    it("calls a same-day pair same, ignoring the time of day", () => {
        // both legs on the 10th but hours apart: comparing the day part, not the
        // full timestamp, is what makes this a same-day transfer
        expect(transferDates(item("2026-03-10T09:30:00", "2026-03-10T23:15:00")).sameDay).toBe(
            true,
        );
    });

    it("calls legs posted on different days not same-day", () => {
        expect(transferDates(item("2026-03-10T23:59:00", "2026-03-11T00:01:00")).sameDay).toBe(
            false,
        );
    });
});
