// monori "Mono" categorical palette — an Observable-10 style qualitative set,
// orange-led so the brand accent leads the series, then distinct hues that stay
// legible against the near-monochrome UI in both light and dark themes.
export const PALETTE = [
    "#ef5a17",
    "#4269d0",
    "#3ca951",
    "#a463f2",
    "#ff8ab7",
    "#6cc5b0",
    "#efb118",
    "#9c6b4e",
    "#97bbf5",
    "#ff725c",
    "#6b4fbb",
    "#9498a0",
];

// income/expense/accent map to the theme's semantic tokens so the data keeps its
// green/red/brand meaning across light & dark; the neutral tokens back the
// "budgeted target" and receding year-over-year lines.
export const SERIES = {
    income: "var(--m-income)",
    expense: "var(--m-expense)",
    accent: "var(--m-accent)",
    warning: "var(--m-warning)",
    hint: "var(--g-color-text-hint)",
    secondary: "var(--g-color-text-secondary)",
};

// number formatter for axis ticks and tooltip values (data is already in rubles)
export const fmtNum = (v) => (v == null ? "" : Math.round(v).toLocaleString("ru-RU"));

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
};
