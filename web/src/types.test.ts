import { describe, expect, expectTypeOf, it } from "vitest";
import type { z } from "zod";
import {
    accountSchema,
    accountTypeSchema,
    budgetCellSchema,
    categoryGroupKindSchema,
    categoryGroupSchema,
    categorySchema,
    connectionSchema,
    connectionStatusSchema,
    goalStatusSchema,
    snapshotSchema,
    transactionPageSchema,
    transactionSchema,
    transactionSourceSchema,
    transactionSplitSchema,
    transferSchema,
    userSchema,
} from "./apiSchemas.js";
import type {
    AccountId,
    AccountResponse,
    BudgetCellResponse,
    CategoryGroupResponse,
    CategoryId,
    CategoryResponse,
    ConnectionResponse,
    IsoDate,
    IsoDateTime,
    Kopecks,
    SnapshotResponse,
    TransactionId,
    TransactionPageResponse,
    TransactionResponse,
    TransactionSplitResponse,
    TransferResponse,
    UserResponse,
} from "./types.js";

describe("API response type contracts", () => {
    it("keeps response aliases derived from Zod schemas", () => {
        expectTypeOf<AccountResponse>().toEqualTypeOf<z.output<typeof accountSchema>>();
        expectTypeOf<CategoryGroupResponse>().toEqualTypeOf<z.output<typeof categoryGroupSchema>>();
        expectTypeOf<CategoryResponse>().toEqualTypeOf<z.output<typeof categorySchema>>();
        expectTypeOf<TransactionSplitResponse>().toEqualTypeOf<
            z.output<typeof transactionSplitSchema>
        >();
        expectTypeOf<TransactionResponse>().toEqualTypeOf<z.output<typeof transactionSchema>>();
        expectTypeOf<BudgetCellResponse>().toEqualTypeOf<z.output<typeof budgetCellSchema>>();
        expectTypeOf<TransferResponse>().toEqualTypeOf<z.output<typeof transferSchema>>();
        expectTypeOf<ConnectionResponse>().toEqualTypeOf<z.output<typeof connectionSchema>>();
        expectTypeOf<SnapshotResponse>().toEqualTypeOf<z.output<typeof snapshotSchema>>();
        expectTypeOf<TransactionPageResponse>().toEqualTypeOf<
            z.output<typeof transactionPageSchema>
        >();
        expectTypeOf<UserResponse>().toEqualTypeOf<z.output<typeof userSchema>>();

        expectTypeOf<AccountId>().toExtend<number>();
        expectTypeOf<CategoryId>().toExtend<number>();
        expectTypeOf<TransactionId>().toExtend<number>();
        expectTypeOf<Kopecks>().toExtend<number>();
        expectTypeOf<IsoDate>().toExtend<string>();
        expectTypeOf<IsoDateTime>().toExtend<string>();
    });

    it("exposes the closed runtime domains", () => {
        expect(accountTypeSchema.options).toEqual(["card", "cash", "savings", "other"]);
        expect(categoryGroupKindSchema.options).toEqual(["income", "expense", "goal"]);
        expect(connectionStatusSchema.options).toContain("connected");
        expect(transactionSourceSchema.options).toContain("manual");
        expect(goalStatusSchema.options).toContain("active");
    });
});
