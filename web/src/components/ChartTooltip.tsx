import { ChartTooltip } from "@mantine/charts";
import type { ReactNode } from "react";
import type { TooltipPayloadEntry, TooltipValueType } from "recharts";
import { chartMoneyUnit, fmtNum, trendUnit } from "../pages/chartTheme.js";

type NullableTooltipItem = Omit<TooltipPayloadEntry, "value" | "graphicalItemId"> & {
    value?: TooltipValueType | null | undefined;
    graphicalItemId?: string | undefined;
};
type RechartsTooltipProps = {
    label?: ReactNode;
    payload?: readonly NullableTooltipItem[];
};

function withUnit(
    payload: readonly NullableTooltipItem[] | undefined,
    getUnit: (name: string) => string,
) {
    return payload
        ?.filter(
            (item): item is NullableTooltipItem & { value: number } =>
                typeof item.value === "number",
        )
        .map((item) => ({
            ...item,
            unit: getUnit(typeof item.name === "string" ? item.name : ""),
        }));
}

export function MoneyChartTooltip({ label, payload }: RechartsTooltipProps) {
    return (
        <ChartTooltip
            label={label}
            payload={withUnit(payload, () => chartMoneyUnit)}
            valueFormatter={fmtNum}
        />
    );
}

export function TrendChartTooltip({ label, payload }: RechartsTooltipProps) {
    return (
        <ChartTooltip
            label={label}
            payload={withUnit(payload, trendUnit)}
            valueFormatter={fmtNum}
        />
    );
}
