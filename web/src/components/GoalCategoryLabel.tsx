import { rub } from "../format.js";
import { Tooltip } from "@mantine/core";
import type { ReactNode } from "react";

interface GoalProgressValue {
    funded: number;
    target: number;
    percent: number;
    status: string;
}

export default function GoalCategoryLabel({
    name,
    progress,
    urgency = null,
}: {
    name: string;
    progress?: GoalProgressValue | null;
    urgency?: ReactNode;
}) {
    if (!progress) return <>{name}</>;
    const label = (
        <span className="goal-label__popup">
            <span>
                {rub(progress.funded)} / {rub(progress.target)} ₽ · {progress.percent}%
            </span>
            {urgency}
        </span>
    );
    return (
        <Tooltip label={label} withArrow openDelay={180} classNames={{ tooltip: "goal-tooltip" }}>
            <span className="goal-label" tabIndex={0}>
                {name}
            </span>
        </Tooltip>
    );
}
