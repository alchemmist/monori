import { z } from "zod";
import type { Snapshot, TransactionPage, User } from "./types.js";

const id = z.number().int().positive();
const nullableId = id.nullable();

export const accountSchema = z.strictObject({
    id,
    name: z.string(),
    type: z.string(),
    icon: z.string(),
    color: z.string(),
    iconImage: z.string().nullable(),
    currency: z.string(),
    sort: z.number(),
    archived: z.boolean(),
    openingBalance: z.number(),
    openingDate: z.string().nullable(),
    connectionId: nullableId,
    bankRef: z.string(),
    cardTails: z.array(z.string()),
});

export const categoryGroupSchema = z.strictObject({
    id,
    name: z.string(),
    sort: z.number(),
    kind: z.string(),
});

export const categorySchema = z.strictObject({
    id,
    groupId: id,
    name: z.string(),
    keywords: z.string(),
    sort: z.number(),
    archived: z.boolean(),
    goalTarget: z.number().nullable(),
    goalStatus: z.string().nullable(),
    goalTargetDate: z.string().nullable(),
});

export const transactionSplitSchema = z.strictObject({
    id,
    categoryId: id,
    amount: z.number(),
    comment: z.string(),
});

export const transactionSchema = z.strictObject({
    id,
    date: z.string(),
    amount: z.number(),
    description: z.string(),
    bankCategory: z.string(),
    mcc: z.string(),
    categoryId: nullableId,
    accountId: id,
    transferId: z.string().nullable(),
    comment: z.string(),
    source: z.string(),
    hidden: z.boolean(),
    splits: z.array(transactionSplitSchema),
});

export const budgetCellSchema = z.strictObject({
    categoryId: id,
    year: z.number().int(),
    month: z.number().int().min(1).max(12),
    amount: z.number(),
});

export const transferSchema = z.strictObject({
    id: z.string(),
    outTxId: id,
    inTxId: id,
    origin: z.string(),
    note: z.string(),
    createdAt: z.string(),
});

export const connectionSchema = z.strictObject({
    id,
    bank: z.string(),
    kind: z.string(),
    status: z.string(),
    lastSync: z.string().nullable(),
    lastError: z.string().nullable(),
    hasCredentials: z.boolean(),
    createdAt: z.string(),
    updatedAt: z.string(),
});

export const snapshotSchema = z.strictObject({
    accounts: z.array(accountSchema),
    groups: z.array(categoryGroupSchema),
    categories: z.array(categorySchema),
    transactions: z.array(transactionSchema),
    transactionsTotal: z.number().int().nonnegative(),
    transfers: z.array(transferSchema),
    budgets: z.array(budgetCellSchema),
    connections: z.array(connectionSchema),
}) satisfies z.ZodType<Snapshot>;

export const transactionPageSchema = z.strictObject({
    total: z.number().int().nonnegative(),
    rows: z.array(transactionSchema),
}) satisfies z.ZodType<TransactionPage>;

export const userSchema = z.strictObject({
    id,
    email: z.email(),
    createdAt: z.string(),
    isAdmin: z.boolean(),
    lastLogin: z.string().nullable(),
    defaultAccountId: nullableId,
}) satisfies z.ZodType<User>;

export const authTokenSchema = z.strictObject({
    access_token: z.string().min(1),
    token_type: z.literal("bearer"),
});
export const entitySchema = z.strictObject({ id });
export const okResponseSchema = z.strictObject({
    ok: z.boolean().optional(),
    set: z.number().int().nonnegative().optional(),
});

export const e2eMutationResponseSchema = z.union([
    entitySchema,
    okResponseSchema,
    z.strictObject({ splits: z.array(transactionSplitSchema) }),
]);

export const parseJson = async <Schema extends z.ZodType>(
    source: { json(): Promise<unknown> },
    schema: Schema,
): Promise<z.output<Schema>> => schema.parse(await source.json());
