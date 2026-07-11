// monori "Mono" categorical palette — an Observable-10 style qualitative set,
// orange-led so the brand accent leads the series, then distinct hues that stay
// legible against the near-monochrome UI in both light and dark themes.
const CATEGORY_PALETTE = [
  "#ef5a17", "#4269d0", "#3ca951", "#a463f2", "#ff8ab7", "#6cc5b0",
  "#efb118", "#9c6b4e", "#97bbf5", "#ff725c", "#6b4fbb", "#9498a0",
];

/** Chart tokens. income/expense/accent map to the theme's semantic tokens so
 * the data keeps its green/red/brand meaning across light & dark; every other
 * series color comes from the qualitative CATEGORY_PALETTE. */
export const C = {
  income: "var(--g-color-text-positive)",
  expense: "var(--g-color-text-danger)",
  accent: "var(--g-color-text-brand)",
  amber: "var(--g-color-text-warning)",
  palette: CATEGORY_PALETTE,
};

export const axisCommon = {
  labels: { style: { fontSize: "11px", fontColor: "var(--m-text-dim)" } },
  lineColor: "var(--m-border)",
  gridColor: "var(--m-border-soft)",
  ticksColor: "var(--m-border)",
};

export const legendCommon = {
  enabled: true,
  itemStyle: { fontColor: "var(--m-text-dim)", fontSize: "12px" },
};
