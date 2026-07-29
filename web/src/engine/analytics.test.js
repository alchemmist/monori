import { describe, expect, it } from "vitest";
import {
    monthlySeries,
    yearTotals,
    merchantKey,
    topMerchants,
    weekdayProfile,
    dayOfMonthProfile,
    txStats,
    incomeStats,
    disciplineMatrix,
    accountBalances,
    categoryYearMatrix,
    categoryTotals,
} from "./analytics.js";
import { buildTxIndex, computeRange, txKey } from "./budget.js";

const snapshot = {
    groups: [
        { id: 1, name: "Salary", kind: "income" },
        { id: 2, name: "Daily", kind: "expense" },
    ],
    categories: [
        { id: 10, groupId: 1, name: "Job" },
        { id: 20, groupId: 2, name: "Groceries" },
        { id: 21, groupId: 2, name: "Fun" },
    ],
    transactions: [
        {
            id: 1,
            date: "2024-01-10",
            amount: 100_000_00,
            categoryId: 10,
            description: "SALARY OOO ROGA",
        },
        {
            id: 2,
            date: "2024-01-15",
            amount: -20_000_00,
            categoryId: 20,
            description: "PYATEROCHKA 1234 MOSCOW",
        },
        {
            id: 3,
            date: "2024-01-20",
            amount: -5_000_00,
            categoryId: 21,
            description: "STEAM PURCHASE 42",
        },
        // Saturday 2024-02-03
        {
            id: 4,
            date: "2024-02-03",
            amount: -10_000_00,
            categoryId: 20,
            description: "PYATEROCHKA 99 MOSCOW",
        },
        {
            id: 5,
            date: "2024-02-05",
            amount: -1_000_00,
            categoryId: null,
            transferId: "t1",
            description: "transfer, uncategorized",
        },
        {
            id: 6,
            date: "2024-02-07",
            amount: -2_000_00,
            categoryId: null,
            description: "UNCATEGORIZED CAFE",
        },
    ],
    budgets: [
        { categoryId: 20, year: 2024, month: 1, amount: 25_000_00 },
        { categoryId: 20, year: 2024, month: 2, amount: 5_000_00 },
        { categoryId: 21, year: 2024, month: 1, amount: 4_000_00 },
    ],
};

describe("monthlySeries", () => {
    it("splits categorized transactions into monthly income/expense", () => {
        const m = monthlySeries(snapshot);
        expect(m).toEqual([
            ["2024-01", { income: 100_000_00, expense: 25_000_00 }],
            ["2024-02", { income: 0, expense: 10_000_00 }],
        ]);
    });

    it("nets a linked positive refund against its expense category in exact kopecks", () => {
        const refunded = {
            ...snapshot,
            transactions: [
                ...snapshot.transactions,
                {
                    id: 7,
                    date: "2024-01-21",
                    amount: 24_01,
                    categoryId: 20,
                    refundOfId: 2,
                    description: "PYATEROCHKA REFUND",
                },
            ],
        };
        expect(monthlySeries(refunded)[0][1].expense).toBe(24_975_99);
        expect(buildTxIndex(refunded.transactions).get(txKey(2024, 1, 20))).toBe(-19_975_99);
    });
});

describe("yearTotals", () => {
    it("aggregates per year with savings rate", () => {
        const [r] = yearTotals(monthlySeries(snapshot));
        expect(r.year).toBe("2024");
        expect(r.net).toBe(65_000_00);
        expect(r.savingsRate).toBeCloseTo(65);
        expect(r.months).toBe(2);
    });
});

describe("merchantKey", () => {
    it("strips terminal ids so the same merchant collapses to one key", () => {
        expect(merchantKey("PYATEROCHKA 1234 MOSCOW")).toBe("PYATEROCHKA MOSCOW");
        expect(merchantKey("OZON *TELECOM 998877")).toBe("OZON TELECOM");
        // digits removed and only the first 3 words kept
        expect(merchantKey("WILDBERRIES 55 A B C D")).toBe("WILDBERRIES A B");
    });

    it("replaces an embedded number with a space, not with nothing", () => {
        // "A1B" must become two words "A B", not the single word "AB"
        expect(merchantKey("A1B")).toBe("A B");
    });
});

describe("topMerchants", () => {
    it("sums both Pyaterochka transactions under one merchant", () => {
        const top = topMerchants(snapshot, "2024");
        const pyat = top.find((m) => m.name.startsWith("PYATEROCHKA"));
        expect(pyat.total).toBe(30_000_00);
        expect(pyat.count).toBe(2);
        expect(top[0]).toBe(pyat);
    });
});

describe("categoryYearMatrix", () => {
    it("spreads each expense category across the twelve months of the year", () => {
        const rows = categoryYearMatrix(snapshot, "2024");
        expect(rows.map((r) => r.name)).toEqual(["Groceries", "Fun"]);
        const [groceries, fun] = rows;
        expect(groceries.monthly).toEqual([20_000_00, 10_000_00, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
        expect(groceries.total).toBe(30_000_00);
        expect(fun.total).toBe(5_000_00);
        // income, transfers and uncategorized rows have no place in an expense chart
        expect(rows.every((r) => r.monthly.length === 12)).toBe(true);
    });

    it("ties out with the expense side of monthlySeries", () => {
        const rows = categoryYearMatrix(snapshot, "2024");
        const perMonth = monthlySeries(snapshot).filter(([k]) => k.startsWith("2024"));
        for (const [key, v] of perMonth) {
            const m = +key.slice(5, 7) - 1;
            const stacked = rows.reduce((s, r) => s + r.monthly[m], 0);
            expect(stacked).toBe(v.expense);
        }
    });

    it("folds the tail past the limit into one Other row", () => {
        const many = {
            groups: [{ id: 2, name: "Daily", kind: "expense" }],
            categories: [1, 2, 3, 4].map((i) => ({ id: i, groupId: 2, name: `C${i}` })),
            transactions: [1, 2, 3, 4].map((i) => ({
                id: i,
                date: "2024-03-05",
                amount: -i * 1_000_00,
                categoryId: i,
                description: `c${i}`,
            })),
        };
        const rows = categoryYearMatrix(many, "2024", { limit: 2 });
        expect(rows.map((r) => r.name)).toEqual(["C4", "C3", "Other"]);
        const other = rows[2];
        expect(other.id).toBe(null);
        // C2 + C1, landing on March like the rows it stands for
        expect(other.total).toBe(3_000_00);
        expect(other.monthly[2]).toBe(3_000_00);
    });

    it("nets a refund against the month it lands in instead of dropping it", () => {
        const refunded = {
            groups: [{ id: 2, name: "Daily", kind: "expense" }],
            categories: [{ id: 20, groupId: 2, name: "Groceries" }],
            transactions: [
                { id: 1, date: "2024-01-10", amount: -5_000_00, categoryId: 20, description: "a" },
                { id: 2, date: "2024-01-20", amount: 2_000_00, categoryId: 20, description: "ref" },
            ],
        };
        const [row] = categoryYearMatrix(refunded, "2024");
        expect(row.monthly[0]).toBe(3_000_00);
        expect(row.total).toBe(3_000_00);
    });

    it("returns nothing for a year without categorized expenses", () => {
        expect(categoryYearMatrix(snapshot, "2019")).toEqual([]);
    });

    it("can build the same year grid for income categories", () => {
        const [salary] = categoryYearMatrix(snapshot, "2024", { kind: "income" });
        expect(salary.name).toBe("Job");
        expect(salary.monthly[0]).toBe(100_000_00);
        expect(salary.total).toBe(100_000_00);
    });

    it("keeps income-category data scoped to the selected year", () => {
        const withPriorIncome = {
            ...snapshot,
            transactions: [
                ...snapshot.transactions,
                { id: 7, date: "2023-06-01", amount: 50_000_00, categoryId: 10 },
            ],
        };
        expect(categoryYearMatrix(withPriorIncome, "2023", { kind: "income" })[0].total).toBe(
            50_000_00,
        );
        expect(categoryYearMatrix(withPriorIncome, "2024", { kind: "income" })[0].total).toBe(
            100_000_00,
        );
    });
});

describe("categoryTotals", () => {
    it("sums all-time expense and income categories separately", () => {
        expect(categoryTotals(snapshot)).toMatchObject([
            { id: 20, name: "Groceries", total: 30_000_00 },
            { id: 21, name: "Fun", total: 5_000_00 },
        ]);
        expect(categoryTotals(snapshot, { kind: "income" })).toMatchObject([
            { id: 10, name: "Job", total: 100_000_00 },
        ]);
    });

    it("drops uncategorized rows and transfer legs", () => {
        const withIgnored = {
            ...snapshot,
            transactions: [
                ...snapshot.transactions,
                { id: 7, date: "2024-02-10", amount: -90_000_00, categoryId: null },
                { id: 8, date: "2024-02-11", amount: -80_000_00, categoryId: 20, transferId: "x" },
            ],
        };
        expect(categoryTotals(withIgnored)).toEqual(categoryTotals(snapshot));
    });
});

describe("weekdayProfile", () => {
    it("buckets spending by weekday, Monday first", () => {
        const w = weekdayProfile(snapshot, "2024");
        expect(w[0]).toBe(20_000_00); // 2024-01-15 is a Monday
        expect(w[5]).toBe(15_000_00); // 2024-01-20 and 2024-02-03 are Saturdays
        expect(w.reduce((s, v) => s + v, 0)).toBe(35_000_00);
    });
});

describe("txStats", () => {
    it("computes count, median and largest expense", () => {
        const s = txStats(snapshot, "2024");
        // ids 2, 3 and 4; uncategorized rows and the transfer leg are out
        expect(s.count).toBe(3);
        expect(s.median).toBe(10_000_00);
        expect(s.largest.amount).toBe(20_000_00);
    });
});

describe("incomeStats", () => {
    it("counts only categorized income and identifies its largest entry", () => {
        const s = incomeStats(snapshot, "2024");
        expect(s.count).toBe(1);
        expect(s.median).toBe(100_000_00);
        expect(s.largest).toMatchObject({ amount: 100_000_00, description: "SALARY OOO ROGA" });
    });

    it("excludes uncategorized deposits and transfer legs", () => {
        const withIgnored = {
            ...snapshot,
            transactions: [
                ...snapshot.transactions,
                { id: 7, date: "2024-02-10", amount: 200_000_00, categoryId: null },
                { id: 8, date: "2024-02-11", amount: 300_000_00, categoryId: 10, transferId: "x" },
            ],
        };
        expect(incomeStats(withIgnored, "2024")).toEqual(incomeStats(snapshot, "2024"));
    });
});

describe("disciplineMatrix", () => {
    it("classifies hits, overruns and unbudgeted spend", () => {
        const results = computeRange(snapshot, 2024, 2024);
        const d = disciplineMatrix(results.get(2024), snapshot.categories, snapshot.groups);
        const groceries = d.rows.find((r) => r.category.id === 20);
        const fun = d.rows.find((r) => r.category.id === 21);
        expect(groceries.cells[0].ratio).toBeCloseTo(0.8); // 20k of 25k
        // Feb budgets 5k but January left 5k in the envelope: 10k of 10k, a hit
        expect(groceries.cells[1].ratio).toBeCloseTo(1);
        expect(groceries.cells[1].available).toBe(10_000_00);
        expect(fun.cells[0].ratio).toBeCloseTo(1.25); // 5k of 4k
        // hits: groceries Jan and Feb; misses: fun Jan → 2/3
        expect(d.hitRate).toBeCloseTo(66.67, 1);
        expect(d.totalOverrun).toBe(1_000_00);
        expect(d.worst.category.id).toBe(21);
    });
});

describe("accountBalances", () => {
    it("counts categorized rows and transfer legs, not unaccepted uncategorized rows", () => {
        const snap = {
            accounts: [
                { id: 1, name: "Card", openingBalance: 10_000_00 },
                { id: 2, name: "Cash", openingBalance: 0 },
            ],
            groups: [],
            categories: [],
            transactions: [
                { id: 1, date: "2024-01-01", amount: -3_000_00, accountId: 1, categoryId: null },
                {
                    id: 2,
                    date: "2024-01-02",
                    amount: -2_000_00,
                    accountId: 1,
                    transferId: "t1",
                    categoryId: null,
                },
                {
                    id: 3,
                    date: "2024-01-02",
                    amount: 2_000_00,
                    accountId: 2,
                    transferId: "t1",
                    categoryId: null,
                },
            ],
        };
        const b = accountBalances(snap);
        // the uncategorized -3000 is outside the ledger until it gets a
        // category — the budget cannot see it, so the balance must not either
        expect(b.get(1)).toBe(10_000_00 - 2_000_00);
        expect(b.get(2)).toBe(2_000_00);
    });

    it("counts categorized rows and reconcile adjustments", () => {
        const snap = {
            accounts: [{ id: 1, name: "Card", openingBalance: 0 }],
            groups: [],
            categories: [],
            transactions: [
                { id: 1, date: "2024-01-01", amount: -3_000_00, accountId: 1, categoryId: 20 },
                {
                    id: 2,
                    date: "2024-01-02",
                    amount: 1_500_00,
                    accountId: 1,
                    categoryId: null,
                    source: "adjustment",
                },
            ],
        };
        expect(accountBalances(snap).get(1)).toBe(-1_500_00);
    });

    it("treats a missing accounts list as empty", () => {
        expect(accountBalances({ transactions: [] }).size).toBe(0);
    });
});

describe("transfers are excluded from income/expense", () => {
    it("monthlySeries ignores rows with a transferId", () => {
        const snap = {
            groups: [{ id: 1, name: "Daily", kind: "expense" }],
            categories: [{ id: 20, groupId: 1, name: "Groceries" }],
            transactions: [
                { id: 1, date: "2024-01-05", amount: -5_000_00, categoryId: 20, transferId: null },
                // a categorized-looking transfer leg must not count as expense
                { id: 2, date: "2024-01-06", amount: -9_000_00, categoryId: 20, transferId: "t1" },
            ],
        };
        const series = monthlySeries(snap);
        expect(series).toEqual([["2024-01", { income: 0, expense: 5_000_00 }]]);
    });
});

describe("monthlySeries edge cases", () => {
    const snap = {
        groups: [{ id: 2, name: "Daily", kind: "expense" }],
        categories: [{ id: 20, groupId: 2, name: "Groceries" }],
        transactions: [
            { id: 1, date: "2024-03-01", amount: -300_00, categoryId: 20 },
            { id: 2, date: "2024-01-01", amount: -100_00, categoryId: 20 },
            // categoryId points at a category that no longer exists → dropped
            { id: 3, date: "2024-02-01", amount: -999_00, categoryId: 777 },
            // uncategorized → dropped
            { id: 4, date: "2024-02-02", amount: -50_00, categoryId: null },
        ],
    };

    it("sorts by month ascending", () => {
        const series = monthlySeries(snap);
        expect(series.map(([k]) => k)).toEqual(["2024-01", "2024-03"]);
    });

    it("drops rows whose category is missing or null", () => {
        const series = monthlySeries(snap);
        // February had only a missing-category and an uncategorized row
        expect(series.find(([k]) => k === "2024-02")).toBeUndefined();
    });
});

describe("yearTotals edge cases", () => {
    it("sorts years ascending and handles a zero-income year", () => {
        const monthly = [
            ["2025-02", { income: 0, expense: 500_00 }],
            ["2024-01", { income: 1_000_00, expense: 400_00 }],
        ];
        const [a, b] = yearTotals(monthly);
        expect(a.year).toBe("2024");
        expect(b.year).toBe("2025");
        // zero income → savings rate is null (not a division by zero)
        expect(b.savingsRate).toBeNull();
        expect(b.net).toBe(-500_00);
        expect(b.avgExpense).toBe(500_00);
        expect(a.savingsRate).toBeCloseTo(60);
    });
});

describe("weekdayProfile ignores non-expense rows", () => {
    it("buckets only real expenses of the year, Monday first", () => {
        const snap = {
            groups: guardGroups,
            categories: guardCategories,
            transactions: [
                // 2024-01-15 is a Monday
                { id: 1, date: "2024-01-15", amount: -1_000_00, categoryId: 20 },
                ...ignoredRows,
            ],
        };
        const w = weekdayProfile(snap, "2024");
        expect(w[0]).toBe(1_000_00);
        expect(w.reduce((s, v) => s + v, 0)).toBe(1_000_00);
    });
});

describe("dayOfMonthProfile", () => {
    const snap = {
        groups: [
            { id: 1, name: "Salary", kind: "income" },
            { id: 2, name: "Daily", kind: "expense" },
        ],
        categories: [
            { id: 10, groupId: 1, name: "Job" },
            { id: 20, groupId: 2, name: "Groceries" },
        ],
        transactions: [
            { id: 1, date: "2024-01-05", amount: -1_000_00, categoryId: 20 },
            { id: 2, date: "2024-03-05", amount: -500_00, categoryId: 20 },
            { id: 3, date: "2024-01-31", amount: -700_00, categoryId: 20 },
            // income category → excluded even though same day
            { id: 4, date: "2024-01-05", amount: 9_999_00, categoryId: 10 },
            // wrong year → excluded
            { id: 5, date: "2023-01-05", amount: -300_00, categoryId: 20 },
            // a positive-amount expense row (a refund) → excluded (amount >= 0)
            { id: 6, date: "2024-01-05", amount: 4_00, categoryId: 20 },
            // uncategorized → excluded
            { id: 7, date: "2024-01-05", amount: -8_00, categoryId: null },
        ],
    };

    it("buckets a year's expenses by day of month", () => {
        const d = dayOfMonthProfile(snap, "2024");
        expect(d).toHaveLength(31);
        expect(d[4]).toBe(1_500_00); // the 5th of Jan + the 5th of Mar
        expect(d[30]).toBe(700_00); // the 31st of Jan
        expect(d.reduce((s, v) => s + v, 0)).toBe(2_200_00);
    });
});

// Rows the year-scoped chart aggregators must ignore: wrong year, an income
// category, a positive amount, and an uncategorized row.
const ignoredRows = [
    { id: 90, date: "2023-01-01", amount: -9_999_00, categoryId: 20, description: "LAST YEAR" },
    { id: 91, date: "2024-01-01", amount: -8_888_00, categoryId: 10, description: "INCOME LEG" },
    { id: 92, date: "2024-01-01", amount: 7_777_00, categoryId: 20, description: "REFUND" },
    {
        id: 93,
        date: "2024-01-01",
        amount: -6_666_00,
        categoryId: null,
        description: "UNCATEGORIZED",
    },
];
const guardGroups = [
    { id: 1, name: "Salary", kind: "income" },
    { id: 2, name: "Daily", kind: "expense" },
];
const guardCategories = [
    { id: 10, groupId: 1, name: "Job" },
    { id: 20, groupId: 2, name: "Shopping" },
];

describe("topMerchants falls back for empty keys", () => {
    const snap = {
        groups: guardGroups,
        categories: guardCategories,
        transactions: [
            {
                id: 1,
                date: "2024-01-01",
                amount: -1_000_00,
                categoryId: 20,
                description: "OZON 123",
            },
            {
                id: 2,
                date: "2024-01-02",
                amount: -2_000_00,
                categoryId: 20,
                description: "OZON 999",
            },
            // an all-digits description reduces to an empty merchant key
            { id: 3, date: "2024-01-03", amount: -500_00, categoryId: 20, description: "123456" },
            ...ignoredRows,
        ],
    };

    it("groups the two OZON rows first, labels the empty key, and ignores non-expenses", () => {
        const top = topMerchants(snap, "2024");
        expect(top).toHaveLength(2); // only OZON and "(no description)"
        expect(top[0]).toEqual({
            name: "OZON",
            fullName: "OZON 123",
            total: 3_000_00,
            count: 2,
        });
        const empty = top.find((m) => m.name === "(no description)");
        expect(empty.total).toBe(500_00);
    });
});

describe("txStats keeps the first of tied-largest expenses", () => {
    const snap = {
        groups: guardGroups,
        categories: guardCategories,
        transactions: [
            { id: 1, date: "2024-01-01", amount: -3_000_00, categoryId: 20, description: "FIRST" },
            { id: 2, date: "2024-01-02", amount: -3_000_00, categoryId: 20, description: "SECOND" },
            { id: 3, date: "2024-01-03", amount: -1_000_00, categoryId: 20, description: "THIRD" },
            // still ignored: wrong year, income category, refund, transfer leg
            ...ignoredRows.filter((r) => r.categoryId != null),
            {
                id: 94,
                date: "2024-01-04",
                amount: -5_000_00,
                categoryId: null,
                transferId: "t1",
                description: "TRANSFER LEG",
            },
        ],
    };

    it("counts only real expenses and does not replace the largest on an equal amount", () => {
        const s = txStats(snap, "2024");
        expect(s.count).toBe(3);
        expect(s.median).toBe(3_000_00);
        expect(s.largest.amount).toBe(3_000_00);
        expect(s.largest.description).toBe("FIRST");
    });

    it("excludes uncategorized outflows from the count", () => {
        const withUncat = {
            ...snap,
            transactions: [
                ...snap.transactions,
                {
                    id: 95,
                    date: "2024-01-05",
                    amount: -6_000_00,
                    categoryId: null,
                    description: "UNCATEGORIZED SPEND",
                },
            ],
        };
        const s = txStats(withUncat, "2024");
        expect(s.count).toBe(3);
        expect(s.largest.description).toBe("FIRST");
    });

    it("excludes an outflow whose categoryId no longer resolves", () => {
        const withDangling = {
            ...snap,
            transactions: [
                ...snap.transactions,
                {
                    id: 96,
                    date: "2024-01-06",
                    amount: -5_500_00,
                    categoryId: 999,
                    description: "X",
                },
            ],
        };
        const s = txStats(withDangling, "2024");
        expect(s.count).toBe(3);
        expect(s.largest.description).toBe("FIRST");
    });
});

describe("accountBalances ignores unknown accounts", () => {
    it("skips transactions whose account is not in the list", () => {
        const snap = {
            accounts: [{ id: 1, name: "Card", openingBalance: 1_000_00 }],
            groups: [],
            categories: [],
            transactions: [
                { id: 1, date: "2024-01-01", amount: -100_00, accountId: 1, categoryId: 20 },
                { id: 2, date: "2024-01-02", amount: -999_00, accountId: 99, categoryId: 20 },
            ],
        };
        const b = accountBalances(snap);
        expect(b.get(1)).toBe(900_00);
        expect(b.has(99)).toBe(false);
        expect(b.size).toBe(1);
    });
});

describe("disciplineMatrix mechanics", () => {
    const groups = [
        { id: 1, name: "Salary", kind: "income" },
        { id: 2, name: "Daily", kind: "expense" },
    ];
    const categories = [
        { id: 10, groupId: 1, name: "Job" },
        { id: 20, groupId: 2, name: "Groceries" },
        { id: 21, groupId: 2, name: "Fun" },
        { id: 22, groupId: 2, name: "Idle" },
        { id: 23, groupId: 2, name: "Impulse" },
    ];
    const zeros = () =>
        Array.from({ length: 12 }, () => ({ budgeted: 0, outflows: 0, balance: 0 }));
    // balances chain the way the engine builds them: max(prev, 0) + budgeted + outflows
    const cat20 = zeros();
    cat20[0] = { budgeted: 1_000_00, outflows: -800_00, balance: 200_00 }; // hit (spent ≤ available)
    cat20[1] = { budgeted: 0, outflows: -500_00, balance: -300_00 }; // 500 of the 200 carried over → overrun 300
    const cat21 = zeros();
    cat21[0] = { budgeted: 1_000_00, outflows: -1_500_00, balance: -500_00 }; // overrun 500
    const cat23 = zeros();
    cat23[0] = { budgeted: 0, outflows: -500_00, balance: -500_00 }; // nothing available → overrun 500
    const yearResult = {
        byCategory: new Map([
            [20, cat20],
            [21, cat21],
            [22, zeros()], // nothing budgeted or spent all year
            [23, cat23],
        ]),
    };

    it("classifies ratios, truncates past upToMonth, and picks the first worst on a tie", () => {
        const d = disciplineMatrix(yearResult, categories, groups, { upToMonth: 1 });

        const g = d.rows.find((r) => r.category.id === 20);
        expect(g.cells[0].ratio).toBeCloseTo(0.8); // 800 of 1000
        expect(g.cells[1].ratio).toBeCloseTo(2.5); // 500 of the 200 left over
        expect(g.cells[2].ratio).toBeNull(); // month past upToMonth
        expect(g.cells[2]).toEqual({ budgeted: 0, available: 0, spent: 0, ratio: null });

        const impulse = d.rows.find((r) => r.category.id === 23);
        expect(impulse.cells[0].ratio).toBe(Infinity); // spent with an empty envelope

        // income category is never a row; the all-zero category is dropped (no active month)
        expect(d.rows.find((r) => r.category.id === 10)).toBeUndefined();
        expect(d.rows.find((r) => r.category.id === 22)).toBeUndefined();

        // hits 1 (cat20 Jan), active 4 (cat20 Jan+Feb, cat21 Jan, cat23 Jan) → 25%
        expect(d.hitRate).toBeCloseTo(25, 1);
        // overruns: cat20 Feb 300 + cat21 Jan 500 + cat23 Jan 500
        expect(d.totalOverrun).toBe(1_300_00);
        // cat21 and cat23 both overran by 500 → the first one encountered wins
        expect(d.worst.category.id).toBe(21);
    });

    it("counts a saved-up envelope spent in one go as its shortfall, not the whole spend", () => {
        // the bug this guards: budgeting 100k a month for a trip and paying 900k
        // for it in July used to report a ~800k overrun, while the envelope was
        // only 200k short — the number the budget page shows
        const snap = {
            groups,
            categories: [{ id: 30, groupId: 2, name: "Vacation" }],
            accounts: [],
            budgets: Array.from({ length: 7 }, (_, m) => ({
                categoryId: 30,
                year: 2024,
                month: m + 1,
                amount: 100_000_00,
            })),
            transactions: [
                { id: 1, date: "2024-07-10", amount: -900_000_00, categoryId: 30, accountId: 1 },
            ],
        };
        const res = computeRange(snap, 2024, 2024);
        const d = disciplineMatrix(res.get(2024), snap.categories, groups, { upToMonth: 6 });
        expect(res.get(2024).byCategory.get(30)[6].balance).toBe(-200_000_00);
        expect(d.totalOverrun).toBe(200_000_00);
    });

    it("returns a null hit rate when no month is active", () => {
        const idleOnly = { byCategory: new Map([[22, zeros()]]) };
        const d = disciplineMatrix(idleOnly, categories, groups);
        expect(d.rows).toEqual([]);
        expect(d.hitRate).toBeNull();
        expect(d.worst).toBeNull();
    });
});

describe("transfer legs are invisible to every income/expense total", () => {
    // a leg that carries a category is the case merging an existing pair can
    // create; nothing downstream may count it as spending
    const withTransfer = {
        ...snapshot,
        transactions: [
            ...snapshot.transactions,
            {
                id: 900,
                date: "2024-01-11",
                amount: -50_000_00,
                categoryId: 20,
                accountId: 1,
                transferId: "x",
                description: "PYATEROCHKA 1234 MOSCOW",
            },
            {
                id: 901,
                date: "2024-01-11",
                amount: 50_000_00,
                categoryId: 20,
                accountId: 2,
                transferId: "x",
                description: "Transfer",
            },
        ],
    };

    it("leaves the monthly series unchanged", () => {
        expect(monthlySeries(withTransfer)).toEqual(monthlySeries(snapshot));
    });

    it("leaves weekday and day-of-month profiles unchanged", () => {
        expect(weekdayProfile(withTransfer, "2024")).toEqual(weekdayProfile(snapshot, "2024"));
        expect(dayOfMonthProfile(withTransfer, "2024")).toEqual(
            dayOfMonthProfile(snapshot, "2024"),
        );
    });

    it("leaves top merchants unchanged", () => {
        expect(topMerchants(withTransfer, "2024")).toEqual(topMerchants(snapshot, "2024"));
    });

    it("leaves the expense stats unchanged", () => {
        expect(txStats(withTransfer, "2024")).toEqual(txStats(snapshot, "2024"));
    });

    it("keeps the budget engine from spending an envelope on a transfer", () => {
        const range = (s) => computeRange({ ...s, budgets: s.budgets ?? [] }, 2024, 2024);
        expect(range(withTransfer)).toEqual(range(snapshot));
    });

    it("still moves the money between the two account balances", () => {
        const accounts = [
            { id: 1, openingBalance: 0 },
            { id: 2, openingBalance: 0 },
        ];
        const balances = accountBalances({ ...withTransfer, accounts });
        expect(balances.get(1)).toBe(-50_000_00);
        expect(balances.get(2)).toBe(50_000_00);
        expect(balances.get(1) + balances.get(2)).toBe(0);
    });
});

describe("categoryYearMatrix keeps a category whose year nets to zero", () => {
    it("shows a spend fully refunded in a later month rather than hiding it", () => {
        // total is 0 but the months are not: a purchase and its refund in
        // different months still happened, so the row stays on the chart
        const snap = {
            groups: [{ id: 2, name: "Daily", kind: "expense" }],
            categories: [{ id: 20, groupId: 2, name: "Electronics" }],
            transactions: [
                {
                    id: 1,
                    date: "2024-01-10",
                    amount: -5_000_00,
                    categoryId: 20,
                    description: "buy",
                },
                { id: 2, date: "2024-06-10", amount: 5_000_00, categoryId: 20, description: "ref" },
            ],
        };
        const rows = categoryYearMatrix(snap, "2024");
        expect(rows).toHaveLength(1);
        expect(rows[0].total).toBe(0);
        expect(rows[0].monthly[0]).toBe(5_000_00);
        expect(rows[0].monthly[5]).toBe(-5_000_00);
    });
});

describe("incomeStats over several deposits", () => {
    const snap = {
        groups: guardGroups,
        categories: [{ id: 10, groupId: 1, name: "Job" }],
        transactions: [
            { id: 1, date: "2024-01-01", amount: 5_000_00, categoryId: 10, description: "A" },
            { id: 2, date: "2024-01-02", amount: 9_000_00, categoryId: 10, description: "B" },
            { id: 3, date: "2024-01-03", amount: 1_000_00, categoryId: 10, description: "C" },
            { id: 4, date: "2024-01-04", amount: 9_000_00, categoryId: 10, description: "D" },
        ],
    };

    it("takes the median from the sorted amounts and keeps the first largest on a tie", () => {
        const s = incomeStats(snap, "2024");
        expect(s.count).toBe(4);
        // sorted [1000, 5000, 9000, 9000] → middle element
        expect(s.median).toBe(9_000_00);
        // the second 9000 must not displace the first one seen
        expect(s.largest).toMatchObject({ amount: 9_000_00, description: "B" });
    });
});

describe("year-scoped aggregators ignore a dangling category", () => {
    const withDangling = (base) => ({
        ...base,
        transactions: [
            ...base.transactions,
            { id: 500, date: "2024-01-07", amount: -4_321_00, categoryId: 4242, description: "X" },
        ],
    });

    it("dayOfMonthProfile drops an outflow whose category no longer resolves", () => {
        const base = {
            groups: guardGroups,
            categories: guardCategories,
            transactions: [{ id: 1, date: "2024-01-05", amount: -1_000_00, categoryId: 20 }],
        };
        expect(dayOfMonthProfile(withDangling(base), "2024")).toEqual(
            dayOfMonthProfile(base, "2024"),
        );
    });

    it("categoryTotals drops a row whose category no longer resolves", () => {
        const base = {
            groups: guardGroups,
            categories: guardCategories,
            transactions: [{ id: 1, date: "2024-01-05", amount: -1_000_00, categoryId: 20 }],
        };
        expect(categoryTotals(withDangling(base))).toEqual(categoryTotals(base));
    });
});

describe("charts vs budget table parity", () => {
    it("categoryYearMatrix totals equal the budget engine's activity to the kopeck", () => {
        // a category with a refund is exactly where a gross-outflow chart and
        // the net budget table drift apart; both must report the same year
        const snap = {
            groups: [{ id: 2, name: "Daily", kind: "expense" }],
            categories: [{ id: 20, groupId: 2, name: "Dating" }],
            budgets: [],
            transactions: [
                {
                    id: 1,
                    date: "2024-03-05",
                    amount: -433_246_00,
                    categoryId: 20,
                    description: "x",
                },
                {
                    id: 2,
                    date: "2024-04-02",
                    amount: 8_470_00,
                    categoryId: 20,
                    description: "refund",
                },
            ],
        };
        const res = computeRange(snap, 2024, 2024).get(2024);
        const engineYear = res.byCategory.get(20).reduce((s, m) => s + m.outflows, 0);
        const [row] = categoryYearMatrix(snap, "2024", { limit: Infinity });
        expect(row.total).toBe(-engineYear);
        expect(row.total).toBe(424_776_00);
    });
});
