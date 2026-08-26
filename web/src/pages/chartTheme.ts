// monori "Mono" categorical palette — an Observable-10 style qualitative set,
// orange-led so the brand accent leads the series, then distinct hues that stay
// legible against the near-monochrome UI in both light and dark themes.
export const PALETTE = [
    "var(--m-chart-1)",
    "var(--m-chart-2)",
    "var(--m-chart-3)",
    "var(--m-chart-4)",
    "var(--m-chart-5)",
    "var(--m-chart-6)",
    "var(--m-chart-7)",
    "var(--m-chart-8)",
    "var(--m-chart-9)",
    "var(--m-chart-10)",
    "var(--m-chart-11)",
    "var(--m-chart-12)",
];

// income/expense/accent map to the theme's semantic tokens so the data keeps its
// green/red/brand meaning across light & dark; the neutral tokens back the
// "budgeted target" and receding year-over-year lines.
export const SERIES = {
    income: "var(--m-chart-income)",
    expense: "var(--m-chart-expense)",
    accent: "var(--m-chart-accent)",
    warning: "var(--m-chart-warning)",
    hint: "var(--g-color-text-hint)",
    secondary: "var(--g-color-text-secondary)",
};

// number formatter for axis ticks and tooltip values (data is already in rubles)
export const fmtNum = (value: number | null | undefined) =>
    value == null ? "" : Math.round(value).toLocaleString("ru-RU");

export const chartMoneyUnit = "\u00a0₽";

export const chartMoney = (value: number) => `${fmtNum(value)}${chartMoneyUnit}`;

export const trendUnit = (seriesName: string) =>
    seriesName === "Savings rate %" ? "%" : chartMoneyUnit;

// shared props for every cartesian Mantine chart (Bar/Line/Area/Composite). The
// grid/axis-text colors are set in CSS via --chart-grid-color/--chart-text-color
// (see dashboard.css) rather than props: CompositeChart leaks those two props to
// the DOM, so keeping them out of here avoids a React unknown-attribute warning.
export const cartesian = {
    withTooltip: true,
    tooltipAnimationDuration: 100,
    strokeDasharray: "3 3",
    tickLine: "none",
    valueFormatter: fmtNum,
    /* recharts' fixed 60px default clips million-scale ruble ticks against the
       card edge; "auto" sizes the axis to the longest label */
    yAxisProps: { width: "auto", tickMargin: 6 },
} as const;
