import { ChartTooltip } from "@mantine/charts";
import type { ReactNode } from "react";
import type { TooltipPayloadEntry, TooltipValueType } from "recharts";
import { fmtNum } from "../pages/chartTheme.js";
import { currencySymbol } from "../currencies.js";
import { useBaseCurrency } from "../store.js";

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
    const unit = `\u00a0${currencySymbol(useBaseCurrency())}`;
    return (
        <ChartTooltip
            label={label}
            payload={withUnit(payload, () => unit)}
            valueFormatter={fmtNum}
        />
    );
}

export function TrendChartTooltip({ label, payload }: RechartsTooltipProps) {
    const unit = `\u00a0${currencySymbol(useBaseCurrency())}`;
    return (
        <ChartTooltip
            label={label}
            payload={withUnit(payload, (name) => (name === "Savings rate %" ? "%" : unit))}
            valueFormatter={fmtNum}
        />
    );
}
