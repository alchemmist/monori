// Gravity Charts' stock qualitative palette (DEFAULT_PALETTE), not re-exported
// from the package root, so mirrored here verbatim.
const DEFAULT_PALETTE = [
  "#4DA2F1", "#FF3D64", "#8AD554", "#FFC636", "#FFB9DD", "#84D1EE", "#FF91A1",
  "#54A520", "#DB9100", "#BA74B3", "#1F68A9", "#ED65A9", "#0FA08D", "#FF7E00",
  "#E8B0A4", "#52A6C5", "#BE2443", "#70C1AF", "#FFB46C", "#DCA3D7",
];

/** Chart tokens straight from Gravity's defaults — no custom palette.
 * income/expense/accent map to Gravity's semantic dark-theme colors so the
 * data keeps its green/red/brand meaning; everything else is DEFAULT_PALETTE. */
export const C = {
  income: "var(--g-color-text-positive)",
  expense: "var(--g-color-text-danger)",
  accent: "var(--g-color-text-brand)",
  amber: "var(--g-color-text-warning)",
  palette: DEFAULT_PALETTE,
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
