import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { login, request } from "./lib/client.js";
import { seed, statement } from "./lib/seed.js";

const workload = __ENV.WORKLOAD || "read";
const duration = __ENV.DURATION || "30s";
const vus = Number(__ENV.VUS || 10);
const errorRate = new Rate("operation_errors");
const operationDuration = new Trend("operation_duration", true);
const workloadRequests = new Counter("workload_requests");

export const options = {
    summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
    scenarios: {
        [workload]: {
            executor: "constant-vus",
            vus,
            duration,
            gracefulStop: "10s",
            tags: { workload },
        },
    },
    thresholds: {
        operation_errors: ["rate<0.005"],
        operation_duration: workload === "import" ? ["p(95)<3000"] : workload === "write" ? ["p(95)<800"] : ["p(95)<300"],
        checks: ["rate>0.995"],
    },
};

export function setup() {
    return seed(workload);
}

function measured(run) {
    const started = Date.now();
    const result = run();
    operationDuration.add(Date.now() - started);
    errorRate.add(!result.ok);
    workloadRequests.add(result.requests);
}

function auth(data) {
    measured(() => ({ ok: Boolean(login(data.email)), requests: 1 }));
}

function read(data) {
    measured(() => {
        const snapshot = request("GET", "/api/snapshot?light=1&limit=500", undefined, data.token, { operation: "snapshot" });
        const transactions = request("GET", `/api/transactions?limit=100&offset=${(__ITER % 5) * 100}`, undefined, data.token, { operation: "transactions-list" });
        const ok = check(snapshot, { "snapshot read is 200": (response) => response.status === 200 }) && check(transactions, { "transaction page is 200": (response) => response.status === 200 });
        return { ok, requests: 2 };
    });
}

function write(data) {
    measured(() => {
        const month = (__ITER % 12) + 1;
        const budget = request(
            "PUT",
            "/api/budgets",
            { categoryId: data.expenseCategoryId, year: 2026, month, amount: 100000 + __ITER },
            data.token,
            { operation: "budget-write" },
        );
        const created = request(
            "POST",
            "/api/transactions",
            {
                date: `2026-${String(month).padStart(2, "0")}-15T12:00:00`,
                amount: -1000 - __ITER,
                accountId: data.accountId,
                description: `write-${__VU}-${__ITER}`,
            },
            data.token,
            { operation: "transaction-create" },
        );
        if (created.status !== 200) return { ok: false, requests: 2 };
        const transactionId = created.json().id;
        const edited = request(
            "PATCH",
            `/api/transactions/${transactionId}`,
            { categoryId: data.expenseCategoryId },
            data.token,
            { operation: "transaction-categorize" },
        );
        return { ok: budget.status === 200 && edited.status === 200, requests: 3 };
    });
}

function importStatement(data) {
    measured(() => {
        const preview = request(
            "POST",
            "/api/import/preview",
            { text: statement(__ITER, __VU), accountId: data.accountId },
            data.token,
            { operation: "import-preview" },
        );
        if (preview.status !== 200) return { ok: false, requests: 1 };
        const rows = preview.json().rows.map((row) => ({ ...row, accountId: data.accountId }));
        const commit = request(
            "POST",
            "/api/import/commit",
            { rows, accountId: data.accountId },
            data.token,
            { operation: "import-commit" },
        );
        return { ok: commit.status === 200, requests: 2 };
    });
}

export default function (data) {
    ({ auth, read, write, import: importStatement })[workload](data);
    sleep(Number(__ENV.THINK_TIME || 0.2));
}
