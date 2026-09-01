import { z } from "zod";

const id = z.number().int().positive();
const nullableId = id.nullable();

export const accountTypeSchema = z.enum(["card", "cash", "savings", "other"]);
export const categoryGroupKindSchema = z.enum(["income", "expense", "goal"]);
export const connectionStatusSchema = z.enum([
    "disconnected",
    "awaiting_sms",
    "connected",
    "error",
    "pending",
]);
export const transactionSourceSchema = z.enum([
    "manual",
    "import",
    "sync",
    "transfer",
    "adjustment",
    "workbook",
    "sheets",
]);
function isTransactionDate(value: string): boolean {
    return (
        z.iso.date().safeParse(value).success ||
        z.iso.datetime({ offset: true, local: true }).safeParse(value).success
    );
}

const transactionDateSchema = z.string().refine(isTransactionDate);
export const transactionCreateSchema = z.strictObject({
    date: transactionDateSchema,
    amount: z.number().refine(Number.isSafeInteger),
    accountId: id,
    description: z.string().optional(),
    bankCategory: z.string().optional(),
    mcc: z.string().optional(),
    categoryId: nullableId.optional(),
    comment: z.string().optional(),
});
export const goalStatusSchema = z.enum(["active", "achieved", "archived"]);

export const accountSchema = z.strictObject({
    id,
    name: z.string(),
    type: accountTypeSchema,
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
    kind: categoryGroupKindSchema,
});

export const categorySchema = z.strictObject({
    id,
    groupId: id,
    name: z.string(),
    keywords: z.string(),
    sort: z.number(),
    archived: z.boolean(),
    goalTarget: z.number().nullable(),
    goalStatus: goalStatusSchema.nullable(),
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
    source: transactionSourceSchema,
    hidden: z.boolean(),
    splits: z.array(transactionSplitSchema),
});

export const budgetCellSchema = z.strictObject({
    categoryId: id,
    year: z.number().int(),
    month: z.number().int().min(1).max(12),
    amount: z.number(),
});

export const transferSchema = z
    .strictObject({
        id: z.string(),
        out_tx_id: id,
        in_tx_id: id,
        origin: z.string(),
        note: z.string(),
        created_at: z.string(),
    })
    .transform(({ out_tx_id: outTxId, in_tx_id: inTxId, created_at: createdAt, ...transfer }) => ({
        ...transfer,
        outTxId,
        inTxId,
        createdAt,
    }));

export const connectionSchema = z.strictObject({
    id,
    bank: z.string(),
    kind: z.string(),
    status: connectionStatusSchema,
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
});

export const transactionPageSchema = z.strictObject({
    total: z.number().int().nonnegative(),
    rows: z.array(transactionSchema),
});

export const userSchema = z.strictObject({
    id,
    email: z.email(),
    createdAt: z.string(),
    isAdmin: z.boolean(),
    lastLogin: z.string().nullable(),
    defaultAccountId: nullableId,
});

export const authTokenSchema = z.strictObject({
    access_token: z.string().min(1),
    token_type: z.literal("bearer"),
});
export const entitySchema = z.strictObject({ id });
export const okResponseSchema = z.strictObject({ ok: z.boolean() });
export const setResponseSchema = z.strictObject({ set: z.number().int().nonnegative() });
export const deltaResponseSchema = z.strictObject({ delta: z.number() });
export const transferIdResponseSchema = z
    .strictObject({ transfer_id: z.string().min(1) })
    .transform(({ transfer_id: transferId }) => ({ transferId }));
export const splitsResponseSchema = z.strictObject({ splits: z.array(transactionSplitSchema) });
export const deletedResponseSchema = z.strictObject({ deleted: id });
export const cancelledResponseSchema = z.strictObject({ cancelled: id });

const transferCandidateSchema = z
    .strictObject({
        out_tx_id: id,
        in_tx_id: id,
        amount: z.number(),
        days: z.number().int().nonnegative(),
        hint: z.boolean(),
        mismatch: z.boolean(),
    })
    .transform(({ out_tx_id: outTxId, in_tx_id: inTxId, ...candidate }) => ({
        ...candidate,
        outTxId,
        inTxId,
    }));

export const transferSuggestionsResponseSchema = z.strictObject({
    rows: z.array(transferCandidateSchema),
    transactions: z.array(transactionSchema),
});

const mergedTransferSchema = z
    .strictObject({
        id: z.string().min(1),
        out_tx_id: id,
        in_tx_id: id,
        amount: z.number(),
        days: z.number().int().nonnegative(),
        hint: z.boolean(),
        mismatch: z.boolean(),
    })
    .transform(({ out_tx_id: outTxId, in_tx_id: inTxId, ...transfer }) => ({
        ...transfer,
        outTxId,
        inTxId,
    }));

export const transferDetectionResponseSchema = z
    .strictObject({
        merged: z.array(mergedTransferSchema),
        suggested: z.number().int().nonnegative(),
    })
    .transform(({ merged, suggested }) => ({
        merged: merged.map((transfer) => transfer.id),
        suggested,
    }));

const importRowResponseSchema = z
    .strictObject({
        date: z.string(),
        amount: z.number(),
        description: z.string(),
        bank_category: z.string(),
        mcc: z.string(),
        card: z.string(),
        accountId: nullableId,
        categoryId: nullableId,
        duplicate: z.boolean(),
        hash: z.string(),
    })
    .transform(({ bank_category: bankCategory, ...row }) => ({ ...row, bankCategory }));

const importErrorSchema = z.strictObject({
    line: z.number().int().positive(),
    error: z.string(),
    raw: z.string(),
});

export const importPreviewSchema = z.strictObject({
    rows: z.array(importRowResponseSchema),
    errors: z.array(importErrorSchema),
});
export const duplicatesResponseSchema = z.strictObject({ duplicates: z.array(z.boolean()) });
export const importResultSchema = z.strictObject({
    inserted: z.number().int().nonnegative(),
    skipped: z.number().int().nonnegative(),
    transfersMerged: z.number().int().nonnegative(),
    transfersSuggested: z.number().int().nonnegative(),
});

const connectorParameterSchema = z
    .strictObject({
        name: z.string(),
        label: z.string(),
        secret: z.boolean(),
        required: z.boolean(),
        help: z.string().nullable(),
    })
    .transform(({ help, ...parameter }) => (help === null ? parameter : { ...parameter, help }));
export const availableConnectorsSchema = z.array(
    z.strictObject({
        bank: z.string(),
        kind: z.string(),
        label: z.string(),
        connectionParams: z.array(connectorParameterSchema),
        accountParams: z.array(connectorParameterSchema),
    }),
);

const syncAccountSchema = z.strictObject({
    accountId: id,
    inserted: z.number().int().nonnegative(),
    skipped: z.number().int().nonnegative(),
    batchId: nullableId,
    dateFrom: z.string().nullable(),
    dateTo: z.string().nullable(),
});
const syncCompleteSchema = z.strictObject({
    status: connectionStatusSchema,
    inserted: z.number().int().nonnegative(),
    skipped: z.number().int().nonnegative(),
    accounts: z.array(syncAccountSchema),
    dateFrom: z.string().nullable(),
    dateTo: z.string().nullable(),
    unmappedTails: z.array(
        z.strictObject({ tail: z.string(), rows: z.number().int().nonnegative() }),
    ),
});
const syncStatusSchema = z.strictObject({
    status: connectionStatusSchema,
    message: z.string().nullable(),
});
export const syncResultSchema = z.union([syncCompleteSchema, syncStatusSchema]);

const workbookErrorSchema = z
    .strictObject({ row: z.number().int().positive(), error: z.string() })
    .transform(({ row: line, error }) => ({ line, error }));
const workbookSlotSchema = z.strictObject({
    key: z.string(),
    marker: z.string(),
    currency: z.string(),
    transactions: z.number().int().nonnegative(),
});
export const workbookPreviewSchema = z.strictObject({
    groups: z.number().int().nonnegative(),
    categories: z.number().int().nonnegative(),
    transactions: z.number().int().nonnegative(),
    transactionsByYear: z.record(z.string(), z.number().int().nonnegative()),
    budgetCells: z.number().int().nonnegative(),
    accountSlots: z.array(workbookSlotSchema),
    warnings: z.array(z.string()),
    errors: z.array(workbookErrorSchema),
    budgetConflicts: z.number().int().nonnegative(),
});
export const workbookResultSchema = z.strictObject({
    groupsCreated: z.number().int().nonnegative(),
    categoriesCreated: z.number().int().nonnegative(),
    inserted: z.number().int().nonnegative(),
    skipped: z.number().int().nonnegative(),
    batches: z.array(
        z.strictObject({
            accountId: id,
            batchId: id,
            inserted: z.number().int().nonnegative(),
        }),
    ),
    budgetsWritten: z.number().int().nonnegative(),
    budgetsSkipped: z.number().int().nonnegative(),
    warnings: z.array(z.string()),
    errors: z.array(workbookErrorSchema),
    cardTailsBound: z.number().int().nonnegative(),
});

const nonnegativeInt = z.number().int().nonnegative();
export const adminOverviewSchema = z.strictObject({
    totals: z.strictObject({
        users: nonnegativeInt,
        transactions: nonnegativeInt,
        accounts: nonnegativeInt,
        connections: nonnegativeInt,
    }),
    dbSizeBytes: nonnegativeInt,
    newUsers7d: nonnegativeInt,
    newUsers30d: nonnegativeInt,
    activeUsers7d: nonnegativeInt,
    registrations: z.array(z.strictObject({ month: z.string(), count: nonnegativeInt })),
});
const adminConnectionSchema = z.strictObject({
    status: connectionStatusSchema,
    lastSync: z.string().nullable(),
    lastError: z.string().nullable(),
});
export const adminUserSummarySchema = z.strictObject({
    id,
    email: z.email(),
    createdAt: z.string(),
    lastLogin: z.string().nullable(),
    isAdmin: z.boolean(),
    accounts: nonnegativeInt,
    transactions: nonnegativeInt,
    lastTransaction: z.string().nullable(),
    budgets: nonnegativeInt,
    connection: adminConnectionSchema.nullable(),
});
const adminTransactionSummarySchema = z.strictObject({
    id,
    date: z.string(),
    amount: z.number(),
    description: z.string(),
    account: z.string(),
    category: z.string().nullable(),
});
export const adminTransactionSchema = adminTransactionSummarySchema.extend({
    mcc: z.string(),
    comment: z.string(),
    source: transactionSourceSchema,
});
export const adminUserDetailSchema = z.strictObject({
    user: userSchema,
    accounts: z.array(
        z.strictObject({
            id,
            name: z.string(),
            type: accountTypeSchema,
            currency: z.string(),
            archived: z.boolean(),
            balance: z.number(),
            transactions: nonnegativeInt,
        }),
    ),
    recentTransactions: z.array(adminTransactionSummarySchema),
    featureUsage: z.array(z.strictObject({ feature: z.string(), count: nonnegativeInt })),
    recentLogins: z.array(z.string()),
});
export const adminActivitySchema = z.strictObject({
    features: z.array(z.strictObject({ feature: z.string(), count: nonnegativeInt })),
    daily: z.array(z.strictObject({ day: z.string(), count: nonnegativeInt })),
    recentLogins: z.array(z.strictObject({ email: z.email(), at: z.string() })),
});
const sqlCellSchema = z.union([z.number(), z.string(), z.null()]);
const adminSqlResultShape = {
    columns: z.array(z.string()),
    rows: z.array(z.array(sqlCellSchema)),
    rowCount: nonnegativeInt,
    truncated: z.boolean(),
    elapsedMs: z.number().nonnegative(),
};
export const adminSqlResultSchema = z.union([
    z.strictObject({ kind: z.enum(["read", "write"]), ...adminSqlResultShape }),
    z.strictObject({ kind: z.literal("dry"), ...adminSqlResultShape, wouldWrite: z.boolean() }),
]);
export const deletedCountResponseSchema = z.strictObject({ deleted: nonnegativeInt });

export const e2eMutationResponseSchema = z.union([
    entitySchema,
    okResponseSchema,
    splitsResponseSchema,
]);

export const parseJson = async <Schema extends z.ZodType>(
    source: { json(): Promise<unknown> },
    schema: Schema,
): Promise<z.output<Schema>> => schema.parse(await source.json());
