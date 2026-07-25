import { test as base, expect } from "@playwright/test";

// Every date-sensitive surface (current-month highlight, YTD, forecasts) reads
// the browser clock, so the suite pins it to one instant and seeds all data
// around it — tests stay deterministic across month/year rollover.
export const FIXED_NOW = new Date("2026-06-15T12:00:00");
export const YEAR = 2026;
export const MONTH = 6; // June, 1-based

let seq = 0;

// Thin typed-ish seed builders over the real API — no mocks, the same
// endpoints the app itself calls. Amounts are integer kopecks, expenses
// negative.
class Api {
    constructor(request, token) {
        this.request = request;
        this.headers = { authorization: `Bearer ${token}` };
    }

    async post(path, data) {
        const res = await this.request.post(path, { data, headers: this.headers });
        expect(res.ok(), `POST ${path} -> ${res.status()}`).toBeTruthy();
        return res.json();
    }

    async put(path, data) {
        const res = await this.request.put(path, { data, headers: this.headers });
        expect(res.ok(), `PUT ${path} -> ${res.status()}`).toBeTruthy();
        return res.json();
    }

    async snapshot() {
        const res = await this.request.get("/api/snapshot", { headers: this.headers });
        expect(res.ok(), `GET /api/snapshot -> ${res.status()}`).toBeTruthy();
        return res.json();
    }

    createAccount(fields = {}) {
        return this.post("/api/accounts", { name: "Card", type: "card", ...fields });
    }

    createGroup(name, kind = "expense") {
        return this.post("/api/groups", { name, kind });
    }

    createCategory(name, groupId, keywords = "") {
        return this.post("/api/categories", { name, groupId, keywords });
    }

    reorderGroups(ids) {
        return this.post("/api/groups/reorder", { ids });
    }

    addTransaction(fields) {
        return this.post("/api/transactions", {
            date: `${YEAR}-06-10T12:00:00`,
            description: "",
            ...fields,
        });
    }

    setBudget(categoryId, year, month, amount) {
        return this.put("/api/budgets", { categoryId, year, month, amount });
    }
}

// Register a brand-new tenant through the real signup API and hand back its
// token plus a seed-builder client. Specs that need several isolated users in
// one scenario (e.g. the workbook round-trip) call this directly.
export async function makeUser(request, tag = "u") {
    const email = `e2e-${tag}-${++seq}-${Date.now()}@example.com`;
    const password = "e2e-password-123";
    const reg = await request.post("/api/auth/register", { data: { email, password } });
    expect(reg.ok(), `register -> ${reg.status()}`).toBeTruthy();
    const tok = await request.post("/api/auth/token", {
        form: { username: email, password },
    });
    expect(tok.ok(), `token -> ${tok.status()}`).toBeTruthy();
    const { access_token: token } = await tok.json();
    return { email, password, token, api: new Api(request, token) };
}

export const test = base.extend({
    // Each test owns its world: a fresh user registered through the real
    // signup API, with a seed-builder client bound to its token. Isolation is
    // per-tenant, so tests parallelize against the one shared stack.
    // playwright's fixture callback is conventionally named `use`, but oxlint
    // reads that as a React hook — `provide` keeps the linter out of it
    user: async ({ request }, provide, testInfo) => {
        await provide(await makeUser(request, `w${testInfo.workerIndex}`));
    },
});

export { expect };

// Programmatic login: pin the clock, drop the real token into localStorage and
// land in the authed app. Specs other than auth.spec use this so their setup
// does not re-test the login form.
export async function openApp(page, user) {
    await page.clock.install({ time: FIXED_NOW });
    await page.addInitScript((token) => localStorage.setItem("monori_token", token), user.token);
    await page.goto("/");
    await expect(page.locator(".sidebar")).toBeVisible();
}

export async function gotoSection(page, label) {
    await page.locator(".sidebar__item", { hasText: label }).first().click();
}

// Swap the signed-in tenant on an already-open page (the clock stays pinned —
// clock.install survives reloads). Registered as another init script because
// openApp's one re-runs on every reload and would put the old token back;
// init scripts run in registration order, so the later tenant wins.
export async function switchUser(page, user) {
    await page.addInitScript((token) => {
        // a token swap is a tenant switch: wipe the previous tenant's persisted
        // UI state (docked tabs etc.) so it cannot leak ids across users
        localStorage.clear();
        localStorage.setItem("monori_token", token);
    }, user.token);
    await page.reload();
    await expect(page.locator(".sidebar")).toBeVisible();
}
