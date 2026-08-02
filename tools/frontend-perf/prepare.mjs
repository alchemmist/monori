import fs from "node:fs/promises";
import { chromium, request } from "@playwright/test";

const [tokenFile] = process.argv.slice(2);
const baseURL = process.env.PERF_BASE_URL;

if (!tokenFile) throw new Error("usage: node prepare.mjs TOKEN_FILE");
if (!baseURL) throw new Error("PERF_BASE_URL is required");

const email = `perf-${Date.now()}@example.com`;
const password = "perf-password-123";
const api = await request.newContext({ baseURL });

try {
    const registration = await api.post("/api/auth/register", {
        data: { email, password },
    });
    if (!registration.ok()) {
        throw new Error(`register failed: ${registration.status()} ${await registration.text()}`);
    }

    const login = await api.post("/api/auth/token", {
        form: { username: email, password },
    });
    if (!login.ok()) throw new Error(`login failed: ${login.status()} ${await login.text()}`);
    const loginBody = await login.json();
    const token = loginBody.access_token;
    if (typeof token !== "string" || token === "") throw new Error("login returned no token");

    const browser = await chromium.launch();
    try {
        const page = await browser.newPage();
        await page.addInitScript((accessToken) => {
            localStorage.setItem("monori_token", accessToken);
        }, token);
        await page.goto(new URL("/settings", baseURL).toString());
        await page.getByRole("heading", { name: "Settings" }).waitFor();
        const addDemo = page.getByRole("button", { name: "Add demo data" });
        await addDemo.waitFor({ state: "visible" });
        await addDemo.click();
        await page.getByText("Demo data added", { exact: true }).waitFor({ timeout: 180000 });
    } finally {
        await browser.close();
    }

    const snapshot = await api.get("/api/snapshot?light=1", {
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!snapshot.ok()) {
        throw new Error(`seed verification failed: ${snapshot.status()} ${await snapshot.text()}`);
    }
    const snapshotBody = await snapshot.json();
    if (
        typeof snapshotBody.transactionsTotal !== "number" ||
        snapshotBody.transactionsTotal < 100
    ) {
        throw new Error("seed verification found fewer than 100 transactions");
    }

    await fs.writeFile(tokenFile, JSON.stringify({ token }) + "\n");
} finally {
    await api.dispose();
}
