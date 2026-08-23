import { sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { login, request } from "./lib/client.js";
import { seed, statement } from "./lib/seed.js";

const journeyErrors = new Rate("journey_errors");
const journeyDuration = new Trend("journey_duration", true);
const workloadRequests = new Counter("workload_requests");

export const options = {
    summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
    scenarios: {
        journey: {
            executor: "constant-vus",
            vus: Number(__ENV.VUS || 10),
            duration: __ENV.DURATION || "30s",
            gracefulStop: "10s",
        },
    },
    thresholds: {
        journey_errors: ["rate<0.005"],
        journey_duration: ["p(95)<5000"],
        checks: ["rate>0.995"],
    },
};

export function setup() {
    return seed("journey");
}

export default function (data) {
    const started = Date.now();
    const token = login(data.email);
    if (!token) {
        journeyErrors.add(true);
        journeyDuration.add(Date.now() - started);
        workloadRequests.add(1);
        sleep(Number(__ENV.THINK_TIME || 0.5));
        return;
    }
    const snapshot = request("GET", "/api/snapshot?light=1", undefined, token, { operation: "journey-budget" });
    const budget = request(
        "PUT",
        "/api/budgets",
        { categoryId: data.expenseCategoryId, year: 2026, month: (__ITER % 12) + 1, amount: 120000 + __ITER },
        token,
        { operation: "journey-budget-write" },
    );
    const preview = request(
        "POST",
        "/api/import/preview",
        { text: statement(__ITER, __VU, 10), accountId: data.accountId },
        token,
        { operation: "journey-import-preview" },
    );
    let commitStatus = 500;
    let requestCount = 5;
    if (preview.status === 200) {
        const rows = preview.json().rows.map((row) => ({ ...row, accountId: data.accountId }));
        commitStatus = request(
            "POST",
            "/api/import/commit",
            { rows, accountId: data.accountId },
            token,
            { operation: "journey-import-commit" },
        ).status;
        requestCount += 1;
    }
    const dashboard = request("GET", "/api/snapshot?light=1", undefined, token, { operation: "journey-dashboard" });
    const failed = [snapshot.status, budget.status, preview.status, commitStatus, dashboard.status].some((status) => status !== 200);
    journeyErrors.add(failed);
    journeyDuration.add(Date.now() - started);
    workloadRequests.add(requestCount);
    sleep(Number(__ENV.THINK_TIME || 0.5));
}
