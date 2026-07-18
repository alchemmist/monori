import { describe, expect, it } from "vitest";
import {
  monthlySeries,
  yearTotals,
  merchantKey,
  topMerchants,
  weekdayProfile,
  dayOfMonthProfile,
  txStats,
  disciplineMatrix,
  accountBalances,
} from "./analytics.js";
import { computeRange } from "./budget.js";

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
      description: "transfer, uncategorized",
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
    expect(s.count).toBe(3);
    expect(s.median).toBe(10_000_00);
    expect(s.largest.amount).toBe(20_000_00);
  });
});

describe("disciplineMatrix", () => {
  it("classifies hits, overruns and unbudgeted spend", () => {
    const results = computeRange(snapshot, 2024, 2024);
    const d = disciplineMatrix(results.get(2024), snapshot.categories, snapshot.groups);
    const groceries = d.rows.find((r) => r.category.id === 20);
    const fun = d.rows.find((r) => r.category.id === 21);
    expect(groceries.cells[0].ratio).toBeCloseTo(0.8); // 20k of 25k
    expect(groceries.cells[1].ratio).toBeCloseTo(2); // 10k of 5k → overrun
    expect(fun.cells[0].ratio).toBeCloseTo(1.25); // 5k of 4k
    // hits: groceries Jan; misses: groceries Feb, fun Jan → 1/3
    expect(d.hitRate).toBeCloseTo(33.33, 1);
    expect(d.totalOverrun).toBe(5_000_00 + 1_000_00);
    expect(d.worst.category.id).toBe(20);
  });
});

describe("accountBalances", () => {
  it("sums opening balance and all transactions per account, transfers included", () => {
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
    expect(b.get(1)).toBe(10_000_00 - 3_000_00 - 2_000_00);
    expect(b.get(2)).toBe(2_000_00);
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

// Rows every year-scoped expense aggregator must ignore: wrong year, an income
// category, a positive amount, and an uncategorized row. Shared to pin the
// guard `!startsWith(year) || categoryId == null || amount >= 0` in each function.
const ignoredRows = [
  { id: 90, date: "2023-01-01", amount: -9_999_00, categoryId: 20, description: "LAST YEAR" },
  { id: 91, date: "2024-01-01", amount: -8_888_00, categoryId: 10, description: "INCOME LEG" },
  { id: 92, date: "2024-01-01", amount: 7_777_00, categoryId: 20, description: "REFUND" },
  { id: 93, date: "2024-01-01", amount: -6_666_00, categoryId: null, description: "UNCATEGORIZED" },
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
      { id: 1, date: "2024-01-01", amount: -1_000_00, categoryId: 20, description: "OZON 123" },
      { id: 2, date: "2024-01-02", amount: -2_000_00, categoryId: 20, description: "OZON 999" },
      // an all-digits description reduces to an empty merchant key
      { id: 3, date: "2024-01-03", amount: -500_00, categoryId: 20, description: "123456" },
      ...ignoredRows,
    ],
  };

  it("groups the two OZON rows first, labels the empty key, and ignores non-expenses", () => {
    const top = topMerchants(snap, "2024");
    expect(top).toHaveLength(2); // only OZON and "(no description)"
    expect(top[0]).toEqual({ name: "OZON", total: 3_000_00, count: 2 });
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
      ...ignoredRows,
    ],
  };

  it("counts only real expenses and does not replace the largest on an equal amount", () => {
    const s = txStats(snap, "2024");
    expect(s.count).toBe(3);
    expect(s.median).toBe(3_000_00);
    expect(s.largest.amount).toBe(3_000_00);
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
        { id: 1, date: "2024-01-01", amount: -100_00, accountId: 1, categoryId: null },
        { id: 2, date: "2024-01-02", amount: -999_00, accountId: 99, categoryId: null },
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
  ];
  const zeros = () => Array.from({ length: 12 }, () => ({ budgeted: 0, outflows: 0, balance: 0 }));
  const cat20 = zeros();
  cat20[0] = { budgeted: 1_000_00, outflows: -800_00, balance: 200_00 }; // hit (spent ≤ budget)
  cat20[1] = { budgeted: 0, outflows: -500_00, balance: -500_00 }; // no budget, spent → ratio Infinity, overrun 500
  const cat21 = zeros();
  cat21[0] = { budgeted: 1_000_00, outflows: -1_500_00, balance: -500_00 }; // overrun 500
  const yearResult = {
    byCategory: new Map([
      [20, cat20],
      [21, cat21],
      [22, zeros()], // nothing budgeted or spent all year
    ]),
  };

  it("classifies ratios, truncates past upToMonth, and picks the first worst on a tie", () => {
    const d = disciplineMatrix(yearResult, categories, groups, { upToMonth: 1 });

    const g = d.rows.find((r) => r.category.id === 20);
    expect(g.cells[0].ratio).toBeCloseTo(0.8); // 800 of 1000
    expect(g.cells[1].ratio).toBe(Infinity); // spent with zero budget
    expect(g.cells[2].ratio).toBeNull(); // month past upToMonth
    expect(g.cells[2]).toEqual({ budgeted: 0, spent: 0, ratio: null });

    // income category is never a row; the all-zero category is dropped (no active month)
    expect(d.rows.find((r) => r.category.id === 10)).toBeUndefined();
    expect(d.rows.find((r) => r.category.id === 22)).toBeUndefined();

    // hits 1 (cat20 Jan), active 3 (cat20 Jan+Feb, cat21 Jan) → 33.33%
    expect(d.hitRate).toBeCloseTo(33.33, 1);
    // overruns: cat20 Feb 500 + cat21 Jan 500
    expect(d.totalOverrun).toBe(1_000_00);
    // both overran by exactly 500 → the first one encountered wins
    expect(d.worst.category.id).toBe(20);
  });

  it("returns a null hit rate when no month is active", () => {
    const idleOnly = { byCategory: new Map([[22, zeros()]]) };
    const d = disciplineMatrix(idleOnly, categories, groups);
    expect(d.rows).toEqual([]);
    expect(d.hitRate).toBeNull();
    expect(d.worst).toBeNull();
  });
});
