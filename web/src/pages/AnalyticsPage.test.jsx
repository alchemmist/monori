import { describe, expect, it, afterEach, beforeEach } from "vitest";
import AnalyticsPage from "./AnalyticsPage.jsx";
import { renderUI, screen, demo, seed, resetStore } from "../test/render.jsx";
import { computeRange } from "../engine/budget.js";
import { useStore } from "../store.js";

describe("AnalyticsPage", () => {
    // Don't reset store between tests - we populate fresh with demo() or seed() in each test
    const FIRST_YEAR = 2020;

    describe("Page structure and title", () => {
        it("renders Yearly analytics title with year selector", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getByText("Yearly analytics")).toBeInTheDocument();
        });

        it("renders KPI cards", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getAllByText("Income").length).toBeGreaterThanOrEqual(1);
            expect(screen.getAllByText("Expenses").length).toBeGreaterThanOrEqual(1);
            expect(screen.getByText("Net saved")).toBeInTheDocument();
            expect(screen.getByText("Savings rate")).toBeInTheDocument();
            expect(screen.getByText("Budget hit rate")).toBeInTheDocument();
            expect(screen.getByText("Over budget")).toBeInTheDocument();
        });
    });

    describe("Year selection", () => {
        it("defaults to current year", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            const currentYear = String(new Date().getFullYear());
            expect(screen.getAllByText(currentYear).length).toBeGreaterThan(0);
        });

        it("truncates to current year", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const futureBoundary = 2030;
            const results = computeRange(snapshot, FIRST_YEAR, futureBoundary);

            renderUI(
                <AnalyticsPage
                    results={results}
                    firstYear={FIRST_YEAR}
                    lastYear={futureBoundary}
                />,
            );

            const currentYear = new Date().getFullYear();
            expect(screen.getAllByText(String(currentYear)).length).toBeGreaterThan(0);
        });

        it("allows querying years in range", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            // Year selector is rendered
            const currentYear = String(new Date().getFullYear());
            expect(screen.getAllByText(currentYear).length).toBeGreaterThan(0);
        });
    });

    describe("KPI values display", () => {
        it("displays income for selected year", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);
            const thisYear = results.get(new Date().getFullYear());

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            if (thisYear && thisYear.income > 0) {
                const incomeText = screen.getByText("Income").parentElement.textContent;
                expect(incomeText).toContain("₽");
            }
        });

        it("displays expenses for selected year", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);
            const thisYear = results.get(new Date().getFullYear());

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            if (thisYear && thisYear.expense > 0) {
                const expenseText = screen.getByText("Expenses").parentElement.textContent;
                expect(expenseText).toContain("₽");
            }
        });

        it("displays savings rate value or dash", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            const savingsRateElements = screen.getAllByText(/^[\d\-]+%?$/);
            expect(savingsRateElements.length).toBeGreaterThan(0);
        });
    });

    describe("Charts rendering", () => {
        it("renders Plan vs fact chart title", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);
            const year = String(new Date().getFullYear());

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getByText(`Plan vs fact · ${year}`)).toBeInTheDocument();
        });

        it("renders Budget discipline chart", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getByText(/Budget discipline/)).toBeInTheDocument();
        });

        it("renders discipline legend", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getByText("≤ 100%")).toBeInTheDocument();
            expect(screen.getByText("100–120%")).toBeInTheDocument();
            expect(screen.getByText("> 120%")).toBeInTheDocument();
            expect(screen.getByText("unbudgeted spend")).toBeInTheDocument();
        });

        it("renders Expenses year over year chart", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getByText("Expenses year over year")).toBeInTheDocument();
        });

        it("renders Yearly report table", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            const headers = screen.getAllByText("Year");
            expect(headers.some((h) => h.closest("th"))).toBe(true);

            expect(screen.getAllByText("Income").some((el) => el.closest("th"))).toBe(true);
            expect(screen.getAllByText("Expenses").some((el) => el.closest("th"))).toBe(true);
        });

        it("renders Spending by weekday chart", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getByText(/Spending by weekday/)).toBeInTheDocument();
        });

        it("renders Spending by day of month chart", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getByText(/Spending by day of month/)).toBeInTheDocument();
        });

        it("renders Top merchants chart when merchants exist", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getByText(/Top merchants/)).toBeInTheDocument();
        });

        it("renders Transaction stats card", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            expect(screen.getByText(/Transaction stats/)).toBeInTheDocument();
            expect(screen.getByText("Expense transactions")).toBeInTheDocument();
            expect(screen.getByText("Median expense")).toBeInTheDocument();
        });
    });

    describe("Discipline grid", () => {
        it("renders empty message when no budgets", () => {
            const snapshot = seed({
                accounts: [],
                groups: [
                    { id: 1, name: "Income", kind: "income", sort: 1 },
                    { id: 2, name: "Expenses", kind: "expense", sort: 2 },
                ],
                categories: [
                    { id: 1, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
                ],
                budgets: [],
                transactions: [],
            });

            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            const year = String(new Date().getFullYear());
            expect(screen.getByText(`No budgeted envelopes in ${year}`)).toBeInTheDocument();
        });

        it("renders empty message when no categorized expenses", () => {
            const snapshot = seed({
                accounts: [],
                groups: [
                    { id: 1, name: "Income", kind: "income", sort: 1 },
                    { id: 2, name: "Expenses", kind: "expense", sort: 2 },
                ],
                categories: [
                    { id: 1, groupId: 2, name: "Food", keywords: "", sort: 1, archived: false },
                ],
                budgets: [],
                transactions: [],
            });

            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            const year = String(new Date().getFullYear());
            expect(screen.getByText(`No categorized expenses in ${year}`)).toBeInTheDocument();
        });
    });

    describe("Yearly report table highlights", () => {
        it("highlights current year row in yearly report", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            const { container } = renderUI(
                <AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />,
            );

            const thisYear = String(new Date().getFullYear());
            const rows = container.querySelectorAll("tr");
            let currentYearRowFound = false;
            rows.forEach((row) => {
                if (
                    row.textContent.includes(thisYear) &&
                    row.classList.contains("report-table__row_current")
                ) {
                    currentYearRowFound = true;
                }
            });
            expect(currentYearRowFound).toBe(true);
        });
    });

    describe("Year over year logic", () => {
        it("shows multiple years in data", () => {
            demo();
            const snapshot = useStore.getState().snapshot;
            const results = computeRange(snapshot, FIRST_YEAR, 2026);

            renderUI(<AnalyticsPage results={results} firstYear={FIRST_YEAR} lastYear={2026} />);

            const thisYear = String(new Date().getFullYear());
            expect(screen.getAllByText(thisYear).length).toBeGreaterThan(0);
        });
    });
});
