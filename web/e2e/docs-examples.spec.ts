import { test, expect } from "./fixtures/fixtures.js";
import { authTokenSchema, parseJson, snapshotSchema, userSchema } from "../src/apiSchemas.js";

test("docs/getting-started.md serves the built application and OpenAPI document", async ({
    request,
}) => {
    const app = await request.get("/");
    expect(app.ok(), `GET / -> ${app.status()}`).toBeTruthy();

    const openapi = await request.get("/openapi.json");
    expect(openapi.ok(), `GET /openapi.json -> ${openapi.status()}`).toBeTruthy();
    expect(await openapi.json()).toMatchObject({ info: { title: "monori" } });
});

test("docs/api.md authentication and snapshot examples work", async ({ request }) => {
    const email = `docs-api-${Date.now()}@example.com`;
    const password = "docs-password-123";
    const registration = await request.post("/api/auth/register", {
        data: { email, password },
    });
    expect(registration.ok(), `register -> ${registration.status()}`).toBeTruthy();
    await parseJson(registration, userSchema);

    const tokenResponse = await request.post("/api/auth/token", {
        form: { username: email, password },
    });
    expect(tokenResponse.ok(), `token -> ${tokenResponse.status()}`).toBeTruthy();
    const { access_token: token } = await parseJson(tokenResponse, authTokenSchema);

    const unauthenticated = await request.get("/api/snapshot");
    expect(unauthenticated.status()).toBe(401);

    const snapshotResponse = await request.get("/api/snapshot", {
        headers: { authorization: `Bearer ${token}` },
    });
    expect(snapshotResponse.ok(), `snapshot -> ${snapshotResponse.status()}`).toBeTruthy();
    const snapshot = await parseJson(snapshotResponse, snapshotSchema);
    expect(snapshot.accounts).toHaveLength(1);
    expect(snapshot.accounts[0]?.name).toBe("Cash");
});
