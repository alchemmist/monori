import {
  Envelope,
  ArrowDownToLine,
  CurlyBrackets,
  ShieldKeyhole,
  ChartColumn,
  CircleRuble,
} from "@gravity-ui/icons";

export const GITHUB_URL = "https://github.com/alchemmist/monori";
export const DEMO_URL = "/demo";

export const FEATURES = [
  {
    icon: Envelope,
    title: "Envelope budgeting",
    text: "Hand money to categories, spend them down, roll the rest forward. The exact YNAB-style math of the spreadsheet it grew from.",
    to: "/budgeting",
  },
  {
    icon: ArrowDownToLine,
    title: "Bank-statement import",
    text: "Paste a statement and it parses, auto-categorizes from your keywords, and de-duplicates — preview before anything is written.",
    to: "/importing",
  },
  {
    icon: ChartColumn,
    title: "Dashboard & analytics",
    text: "KPIs, trends, plan-vs-fact, budget discipline, spending patterns and top merchants — derived live from your ledger.",
    to: "/dashboard-analytics",
  },
  {
    icon: CurlyBrackets,
    title: "Full REST API",
    text: "Every action the UI takes is an HTTP call. Groups, categories, transactions, budgets, import — with optional bearer-token auth.",
    to: "/api",
  },
  {
    icon: CircleRuble,
    title: "Integer-kopeck money",
    text: "Every amount is a whole number of kopecks end to end. No floating point, no rounding drift — totals always reconcile.",
    to: "/data-model",
  },
  {
    icon: ShieldKeyhole,
    title: "Self-hosted & private",
    text: "One container, one SQLite file. Your data never leaves your server. Back it up by copying a single file.",
    to: "/configuration",
  },
];
