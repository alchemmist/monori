import type { z } from "zod";
import type {
    accountSchema,
    budgetCellSchema,
    categoryGroupSchema,
    categorySchema,
    connectionSchema,
    snapshotSchema,
    transactionPageSchema,
    transactionSchema,
    transactionSplitSchema,
    transferSchema,
    userSchema,
} from "./apiSchemas.js";

export type Id = number;
declare const brand: unique symbol;
type Brand<Value, Name extends string> = Value & { readonly [brand]: Name };
export type AccountId = Brand<number, "AccountId">;
export type CategoryId = Brand<number, "CategoryId">;
export type TransactionId = Brand<number, "TransactionId">;
export type Kopecks = Brand<number, "Kopecks">;
export type IsoDate = Brand<string, "IsoDate">;
export type IsoDateTime = Brand<string, "IsoDateTime">;

export const accountId = (value: number): AccountId => value as AccountId;
export const categoryId = (value: number): CategoryId => value as CategoryId;
export const transactionId = (value: number): TransactionId => value as TransactionId;
export const kopecks = (value: number): Kopecks => value as Kopecks;
export const isoDate = (value: string): IsoDate => value as IsoDate;
export const isoDateTime = (value: string): IsoDateTime => value as IsoDateTime;

export type AccountResponse = z.infer<typeof accountSchema>;
export type CategoryGroupResponse = z.infer<typeof categoryGroupSchema>;
export type CategoryResponse = z.infer<typeof categorySchema>;
export type TransactionSplitResponse = z.infer<typeof transactionSplitSchema>;
export type TransactionResponse = z.infer<typeof transactionSchema>;
export type BudgetCellResponse = z.infer<typeof budgetCellSchema>;
export type TransferResponse = z.infer<typeof transferSchema>;
export type ConnectionResponse = z.infer<typeof connectionSchema>;
export type SnapshotResponse = z.infer<typeof snapshotSchema>;
export type TransactionPageResponse = z.infer<typeof transactionPageSchema>;
export type UserResponse = z.infer<typeof userSchema>;
export type ThemeMode = "light" | "dark";

export interface Account {
    id: Id;
    name: string;
    type: string;
    icon: string;
    color: string;
    iconImage: string | null;
    currency: string;
    sort: number;
    archived: boolean;
    openingBalance?: number;
    openingDate?: string | null;
    connectionId?: Id | null;
    bankRef?: string | null;
    cardTails?: string[];
}

export interface CategoryGroup {
    id: Id;
    name: string;
    sort?: number;
    kind: string;
}

export interface Category {
    id: Id;
    groupId: Id;
    name: string;
    keywords: string;
    sort: number;
    archived: boolean;
    goalTarget?: number | null;
    goalStatus?: string | null;
    goalTargetDate?: string | null;
}

export interface TransactionSplit {
    id: Id | string;
    categoryId: Id;
    amount: number;
    comment: string;
    accountId?: Id | null;
}

export interface Transaction {
    id: Id;
    date: string;
    amount: number;
    description: string;
    bankCategory: string;
    mcc?: string;
    categoryId: Id | null;
    accountId: Id;
    transferId: string | null;
    comment: string;
    source?: string;
    hidden?: boolean;
    splits?: TransactionSplit[];
}

export interface BudgetCell {
    categoryId: Id;
    year: number;
    month: number;
    amount: number;
}

export interface Transfer {
    id: string;
    outTxId: Id;
    inTxId: Id;
    origin: string;
    note: string;
    createdAt?: string | null;
}

export interface Connection {
    id: Id;
    bank: string;
    kind: string;
    status: string;
    lastSync: string | null;
    lastError: string | null;
    hasCredentials: boolean;
    createdAt: string;
    updatedAt: string;
}

export interface Snapshot {
    accounts: Account[];
    groups: CategoryGroup[];
    categories: Category[];
    transactions: Transaction[];
    transactionsTotal?: number;
    transfers: Transfer[];
    budgets: BudgetCell[];
    connections?: Connection[];
}

export interface User {
    id: Id;
    email: string;
    createdAt?: string | null;
    isAdmin?: boolean;
    lastLogin?: string | null;
    defaultAccountId?: Id | null;
}

export interface AdminOverview {
    totals: { users: number; transactions: number; accounts: number; connections: number };
    dbSizeBytes: number | null;
    newUsers7d: number;
    newUsers30d: number;
    activeUsers7d: number;
    registrations: Array<{ month: string; count: number }>;
}

export interface AdminConnectionSummary {
    status: string;
    lastSync: string | null;
    lastError: string | null;
}

export interface AdminUserSummary extends User {
    accounts: number;
    transactions: number;
    lastTransaction: string | null;
    budgets: number;
    connection?: AdminConnectionSummary | null;
}

export interface AdminTransaction {
    id: Id;
    date: string;
    amount: number;
    description: string;
    account: string;
    category?: string | null;
    mcc?: string | null;
    comment?: string | null;
    source?: string | null;
}

export interface AdminUserDetail {
    user: User;
    accounts: Array<{
        id: Id;
        name: string;
        type?: string;
        currency?: string;
        archived?: boolean;
        balance: number;
        transactions: number;
    }>;
    recentTransactions: AdminTransaction[];
    featureUsage: Array<{ feature: string; count: number }>;
    recentLogins: string[];
}

export interface AdminActivity {
    features: Array<{ feature: string; count: number }>;
    daily: Array<{ day: string; count: number }>;
    recentLogins: Array<{ email: string; at: string }>;
}

export type SqlCell = number | string | null;
export interface AdminSqlResult {
    kind: "read" | "write" | "dry";
    columns: string[];
    rows: SqlCell[][];
    rowCount: number;
    truncated?: boolean;
    elapsedMs: number;
    wouldWrite?: boolean;
}

export interface ToastMessage {
    title: string;
    theme?: string;
    content?: string;
}

export interface TransactionPage {
    total: number;
    rows: Transaction[];
}

export interface TransactionCreate {
    date: string;
    amount: number;
    accountId: Id;
    description?: string;
    bankCategory?: string;
    mcc?: string;
    categoryId?: Id | null;
    comment?: string;
}

export type TransactionPatch = Partial<
    Pick<
        Transaction,
        | "date"
        | "amount"
        | "accountId"
        | "description"
        | "bankCategory"
        | "mcc"
        | "categoryId"
        | "comment"
        | "hidden"
    >
>;

export type AccountCreate = Pick<Account, "name"> &
    Partial<Omit<Account, "id" | "name" | "sort" | "archived">>;
export type AccountPatch = Partial<Omit<Account, "id" | "sort">>;
export type CategoryCreate = Pick<Category, "name" | "groupId"> &
    Partial<Pick<Category, "keywords" | "goalTarget" | "goalTargetDate">>;
export type CategoryPatch = Partial<Omit<Category, "id" | "sort">>;

export interface TransferCreate {
    fromAccountId: Id;
    toAccountId: Id;
    amount: number;
    date: string;
    comment?: string;
}

export interface TransferPair {
    outTxId: Id;
    inTxId: Id;
    note?: string;
}

export interface TransferSuggestion extends TransferPair {
    amount: number;
    days: number;
    hint?: boolean;
    mismatch?: boolean;
}

export interface ImportRow {
    date: string;
    amount: number;
    description: string;
    bankCategory?: string;
    mcc?: string;
    categoryId?: Id | null;
    accountId?: Id | null;
    comment?: string;
    duplicate?: boolean;
    card?: string;
    hash?: string;
}

export interface ImportPreview {
    rows: ImportRow[];
    errors: Array<{ line: number; error: string; raw?: string }>;
}

export interface ImportResult {
    inserted?: number;
    imported?: number;
    skipped?: number;
    demo?: boolean;
}

interface ConnectorParameter {
    name: string;
    label: string;
    required: boolean;
    secret?: boolean;
    type?: string;
    help?: string;
}

export interface AvailableConnector {
    bank: string;
    kind: string;
    label: string;
    connectionParams: ConnectorParameter[];
    accountParams: ConnectorParameter[];
}

export interface SyncResult {
    status: string;
    message?: string | null;
    inserted?: number;
    skipped?: number;
    accounts?: Array<{
        accountId: Id;
        inserted: number;
        skipped: number;
        batchId: Id | null;
        dateFrom: string | null;
        dateTo: string | null;
    }>;
    dateFrom?: string | null;
    dateTo?: string | null;
    unmappedTails?: Array<{ tail: string; rows: number }>;
}

interface WorkbookSlot {
    key: string;
    marker: string | null;
    currency: string;
    transactions?: number;
}

export interface WorkbookPreview {
    groups: number;
    categories: number;
    transactions: number;
    budgetCells: number;
    budgetConflicts: number;
    errors: Array<string | { line: number; error?: string; raw?: string }>;
    warnings: string[];
    accountSlots: WorkbookSlot[];
}

export interface WorkbookResult {
    groupsCreated: number;
    categoriesCreated: number;
    inserted: number;
    skipped: number;
    batches?: Array<{ accountId: Id; batchId: Id; inserted: number }>;
    budgetsWritten: number;
    budgetsSkipped?: number;
    cardTailsBound?: number;
    warnings?: string[];
    errors?: Array<{ line: number; error: string; raw?: string }>;
}

export interface TabDescriptor {
    id: number;
    key: string | null;
    kind: string;
    props: Record<string, unknown>;
    width?: number;
}
