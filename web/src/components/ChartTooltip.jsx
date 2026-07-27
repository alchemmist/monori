import { ChartTooltip } from "@mantine/charts";
import { chartMoneyUnit, fmtNum, trendUnit } from "../pages/chartTheme.js";

function withUnit(payload, getUnit) {
    return payload
        ?.filter((item) => item.value != null)
        .map((item) => ({ ...item, unit: getUnit(item.name) }));
}

export function MoneyChartTooltip({ label, payload, ...props }) {
    return (
        <ChartTooltip
            label={label}
            payload={withUnit(payload, () => chartMoneyUnit)}
            valueFormatter={fmtNum}
            {...props}
        />
    );
}

export function TrendChartTooltip({ label, payload, ...props }) {
    return (
        <ChartTooltip
            label={label}
            payload={withUnit(payload, trendUnit)}
            valueFormatter={fmtNum}
            {...props}
        />
    );
}
