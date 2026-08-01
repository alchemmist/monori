import { describe, expect, it } from "vitest";
import { authTokenSchema, snapshotSchema } from "./apiSchemas.js";

const snapshot = {
    accounts: [
        {
            id: 1,
            name: "Cash",
            type: "cash",
            icon: "wallet",
            color: "#000000",
            iconImage: null,
            currency: "RUB",
            sort: 1,
            archived: false,
            openingBalance: 0,
            openingDate: null,
            connectionId: null,
            bankRef: "",
            cardTails: [],
        },
    ],
    groups: [{ id: 1, name: "Living", sort: 1, kind: "expense" }],
    categories: [
        {
            id: 1,
            groupId: 1,
            name: "Food",
            keywords: "",
            sort: 1,
            archived: false,
            goalTarget: null,
            goalStatus: null,
            goalTargetDate: null,
        },
    ],
    transactions: [
        {
            id: 1,
            date: "2026-06-10T12:00:00",
            amount: -100,
            description: "Lunch",
            bankCategory: "",
            mcc: "",
            categoryId: 1,
            accountId: 1,
            transferId: null,
            comment: "",
            source: "manual",
            hidden: false,
            splits: [],
        },
    ],
    transactionsTotal: 1,
    transfers: [],
    budgets: [{ categoryId: 1, year: 2026, month: 6, amount: 10_000 }],
    connections: [],
};

describe("API runtime contracts", () => {
    it("accepts a complete snapshot response", () => {
        expect(snapshotSchema.parse(snapshot)).toEqual(snapshot);
    });

    it("rejects unknown fields at nested boundaries", () => {
        const malformed = structuredClone(snapshot);
        Object.assign(malformed.transactions[0]!, { unexpected: true });

        expect(() => snapshotSchema.parse(malformed)).toThrow();
    });

    it("rejects invalid nested values", () => {
        const malformed = structuredClone(snapshot);
        malformed.budgets[0]!.month = 13;

        expect(() => snapshotSchema.parse(malformed)).toThrow();
    });

    it("requires the complete OAuth token response", () => {
        expect(() => authTokenSchema.parse({ access_token: "token" })).toThrow();
        expect(authTokenSchema.parse({ access_token: "token", token_type: "bearer" })).toEqual({
            access_token: "token",
            token_type: "bearer",
        });
    });
});
