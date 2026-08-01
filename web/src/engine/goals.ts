import type { BudgetCell, Category } from "../types.js";

type GoalCategory = {
    id: Category["id"];
    goalTarget?: Category["goalTarget"] | undefined;
    archived?: Category["archived"];
};

/** Goal progress is allocations-to-date; purchases never drain it. */
export function goalProgress(
    goal: GoalCategory,
    budgets: BudgetCell[],
    year: number,
    month: number,
) {
    const funded = budgets.reduce((sum, b) => {
        if (b.categoryId !== goal.id) return sum;
        if (b.year > year || (b.year === year && b.month > month)) return sum;
        return sum + b.amount;
    }, 0);
    const target = goal.goalTarget ?? 0;
    const percent =
        target > 0 ? Math.max(0, Math.min(100, Math.round((funded / target) * 100))) : 0;
    const status =
        goal.archived === true
            ? "archived"
            : target > 0 && funded >= target
              ? "achieved"
              : "active";
    return { funded, target, percent, status };
}
