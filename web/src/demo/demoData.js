/**
 * Synthetic sample dataset for the public /demo page. Deterministic (seeded),
 * no real figures — generated so every screen looks populated: income vs
 * expenses over ~1.5 years, a full-year budget grid, and a long transaction
 * list. Amounts are integer kopecks, dates are YYYY-MM-DD, matching the shape
 * the API's /snapshot returns.
 */

const R = (rub) => Math.round(rub * 100); // rubles -> kopecks

function rng(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = rng(20260711);
const pick = (arr) => arr[Math.floor(rand() * arr.length)];
const between = (a, b) => a + rand() * (b - a);

const GROUPS = [
  { id: 1, name: "Income", kind: "income" },
  { id: 2, name: "Fixed expenses", kind: "expense" },
  { id: 3, name: "Daily living", kind: "expense" },
  { id: 4, name: "Lifestyle", kind: "expense" },
  { id: 5, name: "Savings", kind: "expense" },
];

// [groupId, name, keywords, monthlyBudgetRub, txPerMonth, [minRub, maxRub], merchants[]]
const CATS = [
  [1, "Salary", "payroll|salary", 0, 0, [0, 0], ["Acme Corp payroll"]],
  [1, "Freelance", "invoice|freelance", 0, 0, [0, 0], ["Client invoice"]],

  [2, "Rent", "rent|landlord", 65000, 1, [65000, 65000], ["Landlord"]],
  [2, "Utilities", "utility|electric|water", 8000, 1, [6500, 9500], ["Utility Co"]],
  [
    2,
    "Internet & mobile",
    "internet|mobile|carrier",
    1800,
    2,
    [700, 1200],
    ["Mobile Carrier", "Fiber ISP"],
  ],
  [
    2,
    "Subscriptions",
    "streaming|subscription",
    2400,
    3,
    [199, 1290],
    ["Streaming+", "Music One", "Cloud Drive", "News Daily"],
  ],

  [
    3,
    "Groceries",
    "market|grocery|supermarket",
    36000,
    13,
    [350, 4200],
    ["Green Grocer", "Daily Market", "Fresh Mart", "Corner Store"],
  ],
  [
    3,
    "Cafes & restaurants",
    "cafe|restaurant|coffee",
    13000,
    9,
    [250, 2600],
    ["Corner Cafe", "Sushi Place", "Burger Yard", "Bean Bar"],
  ],
  [
    3,
    "Transport",
    "transit|taxi|ride|fuel",
    5500,
    12,
    [80, 900],
    ["City Transit", "QuickRide", "Fuel Stop"],
  ],
  [
    3,
    "Health & pharmacy",
    "pharmacy|clinic|health",
    3500,
    2,
    [400, 3200],
    ["Pharmacy Plus", "City Clinic"],
  ],

  [
    4,
    "Clothes",
    "clothes|apparel|fashion",
    7000,
    2,
    [1200, 6800],
    ["Fashion Store", "Shoe Room", "Outfitters"],
  ],
  [
    4,
    "Entertainment",
    "cinema|game|event",
    5500,
    4,
    [400, 2800],
    ["Cinema", "Game Store", "Concert Hall"],
  ],
  [4, "Gifts", "gift|present", 3000, 1, [1000, 5000], ["Gift Shop"]],

  [5, "Emergency fund", "", 15000, 0, [0, 0], []],
  [5, "Vacation", "", 12000, 0, [0, 0], []],
];

function build() {
  const categories = CATS.map(([groupId, name, keywords], i) => ({
    id: i + 1,
    groupId,
    name,
    keywords,
    sort: i,
    archived: false,
  }));
  const catId = new Map(categories.map((c) => [c.name, c.id]));

  // month range: 2025-01 .. 2026-07 (partial current year)
  const months = [];
  for (let y = 2025; y <= 2026; y++) {
    for (let m = 1; m <= 12; m++) {
      if (y === 2026 && m > 7) break;
      months.push([y, m]);
    }
  }

  const budgets = [];
  const transactions = [];
  let tid = 1;
  const day2 = (n) => String(n).padStart(2, "0");

  for (const [y, m] of months) {
    // budgets for every expense category
    for (const [groupId, name, , budgetRub] of CATS) {
      if (groupId === 1 || !budgetRub) continue;
      budgets.push({ categoryId: catId.get(name), year: y, month: m, amount: R(budgetRub) });
    }

    // income: salary every month, freelance ~40% of months
    transactions.push({
      id: tid++,
      date: `${y}-${day2(m)}-05`,
      amount: R(Math.round(between(178000, 184000))),
      description: "Acme Corp payroll",
      bankCategory: "Salary",
      categoryId: catId.get("Salary"),
      comment: "",
    });
    if (rand() < 0.4) {
      transactions.push({
        id: tid++,
        date: `${y}-${day2(m)}-${day2(10 + Math.floor(rand() * 12))}`,
        amount: R(Math.round(between(8000, 24000))),
        description: "Client invoice",
        bankCategory: "Transfer",
        categoryId: catId.get("Freelance"),
        comment: "",
      });
    }

    // expenses per category
    for (const [groupId, name, , , perMonth, [lo, hi], merchants] of CATS) {
      if (groupId === 1 || !perMonth) continue;
      const n = Math.max(1, Math.round(perMonth * between(0.7, 1.15)));
      for (let k = 0; k < n; k++) {
        const rub = Math.round(between(lo, hi));
        transactions.push({
          id: tid++,
          date: `${y}-${day2(m)}-${day2(1 + Math.floor(rand() * 27))}`,
          amount: -R(rub),
          description: pick(merchants),
          bankCategory: name,
          categoryId: catId.get(name),
          comment: "",
        });
      }
    }
  }

  transactions.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : b.id - a.id));

  return { groups: GROUPS, categories, budgets, transactions };
}

export const demoSnapshot = build();
