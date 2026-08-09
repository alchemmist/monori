import { BASE_URL, PASSWORD, json, login, request } from "./client.js";

function importRows(accountId, count, prefix) {
    return Array.from({ length: count }, (_, index) => ({
        date: `2026-${String((index % 12) + 1).padStart(2, "0")}-${String((index % 27) + 1).padStart(2, "0")}T12:00:00`,
        amount: index % 5 === 0 ? 250000 : -1000 - index,
        description: `${prefix}-${index}`,
        bankCategory: index % 5 === 0 ? "Income" : "Expenses",
        mcc: index % 5 === 0 ? "" : "5411",
        accountId,
        categoryId: null,
    }));
}

export function seed(workload) {
    const email = `performance-${workload}-${__ENV.VUS || 1}@example.com`;
    request("POST", "/api/auth/register", { email, password: PASSWORD });
    const token = login(email, true);
    const headers = { token, tags: { operation: "seed" } };
    const snapshot = json(request("GET", "/api/snapshot?light=1", undefined, token, headers.tags), "snapshot");
    const accountId = snapshot.accounts[0].id;
    const expenseGroupId = json(
        request("POST", "/api/groups", { name: "Expenses", kind: "expense" }, token, headers.tags),
        "expense group",
    ).id;
    const incomeGroupId = json(
        request("POST", "/api/groups", { name: "Income", kind: "income" }, token, headers.tags),
        "income group",
    ).id;
    const expenseCategoryId = json(
        request(
            "POST",
            "/api/categories",
            { name: "Groceries", groupId: expenseGroupId, keywords: "Market|Shop" },
            token,
            headers.tags,
        ),
        "expense category",
    ).id;
    const incomeCategoryId = json(
        request(
            "POST",
            "/api/categories",
            { name: "Salary", groupId: incomeGroupId, keywords: "Payroll" },
            token,
            headers.tags,
        ),
        "income category",
    ).id;
    json(
        request(
            "POST",
            "/api/import/commit",
            { rows: importRows(accountId, Number(__ENV.SEED_TRANSACTIONS || 500), `seed-${workload}`), accountId },
            token,
            headers.tags,
        ),
        "transaction seed",
    );
    json(
        request(
            "POST",
            "/api/budgets/bulk",
            {
                cells: Array.from({ length: 12 }, (_, index) => ({
                    categoryId: expenseCategoryId,
                    year: 2026,
                    month: index + 1,
                    amount: 100000,
                })),
            },
            token,
            headers.tags,
        ),
        "budget seed",
    );
    return { email, token, accountId, expenseCategoryId, incomeCategoryId, baseUrl: BASE_URL };
}

export function statement(iteration, vu, count = 25) {
    return Array.from({ length: count }, (_, index) => {
        const day = String((index % 27) + 1).padStart(2, "0");
        const amount = String(100 + index);
        return `${day}.07.2026 12:00:00\t${day}.07.2026\t*0001\tOK\t-${amount},00\tRUB\t-${amount},00\tRUB\t\tSupermarkets\t5411\tLoad ${vu}-${iteration}-${index}`;
    }).join("\n");
}
