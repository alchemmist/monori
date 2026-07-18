import { describe, expect, it } from "vitest";
import {
  monthlySeries,
  yearTotals,
  merchantKey,
  topMerchants,
  weekdayProfile,
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
