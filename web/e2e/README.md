# e2e — the cap of the testing trophy

Real, mock-free end-to-end tests: Playwright drives the **production web
build** (nginx) against the **real API** and a **throwaway database**, all
inside an isolated compose stack (`deploy/docker-compose.test.yml`). Nothing
here touches the dev database or dev servers.

## Run it

```sh
make t-slow          # brings the stack up, runs the suite, tears it down
make t-slow-ui       # playwright's interactive ui: run tests on click, time-travel steps
```

CI runs the exact same target. To iterate on specs without rebuilding the
stack every time, keep it running yourself:

```sh
docker compose -f deploy/docker-compose.test.yml -p monori-e2e up --build -d
cd web && npx playwright test              # E2E_BASE_URL defaults to :8078
npx playwright test --ui                   # or headed/interactive
docker compose -f deploy/docker-compose.test.yml -p monori-e2e down -v
```

## Writing a spec

- Import `test` from `./fixtures/fixtures.js`, not from `@playwright/test`.
  The `user` fixture registers a **fresh user through the real signup API**
  for every test — that per-tenant isolation is what lets tests run in
  parallel and in any order against one shared stack. Never reuse another
  test's data.
- Seed through `user.api` (`createGroup`, `createCategory`, `addTransaction`,
  `setBudget`, …) — thin builders over the real endpoints. No mocks; if a
  builder is missing, add one that calls the real API.
- Start with `openApp(page, user)`: it pins the browser clock to `FIXED_NOW`
  (2026-06-15) and logs in programmatically by dropping the real token into
  `localStorage`. Only `auth.spec.js` drives the login form itself.
- Express all seeded dates relative to `FIXED_NOW`/`YEAR`/`MONTH` so specs
  stay deterministic across month and year rollover.
- Keep the cap small: a handful of critical journeys. Exhaustive coverage
  belongs in the engine unit tests and backend integration tests.
- Multi-user journeys (like the workbook round-trip) create extra tenants with
  `makeUser(request)` and swap them on the open page with `switchUser`.

`fixtures/template-workbook.xlsx` is a miniature of the live YNAB-like
template the migration importer targets; regenerate it (and its importer
self-check) with `cd server && uv run python ../scripts/make-e2e-workbook.py`.
