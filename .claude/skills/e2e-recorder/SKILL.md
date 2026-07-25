---
name: e2e-recorder
description: >
    Author a new Playwright e2e test by demonstrating it live. The user describes
    a scenario in plain words; the agent drives a real, visible Chrome window
    through it step by step against the isolated e2e stack while the user watches
    and corrects; on "record it", the agent turns the walkthrough into a spec in
    web/e2e/ and runs it to green. Use whenever the user wants to add or prototype
    an e2e test interactively.
---

# e2e-recorder — demonstrate first, codify second

The flow has four phases. Never skip the live walkthrough: its whole point is
that the user watches the browser and corrects the scenario **before** any code
is written.

## Phase 1 — stand the stack up (keep it up)

Do NOT use `make t-slow` here — it tears the stack down when it exits. Bring
the e2e stack up manually and leave it running for the whole session:

```sh
podman compose -f deploy/docker-compose.test.yml -p monori-e2e up --build -d
curl -fsS http://localhost:8078/openapi.json   # poll until it answers
```

(`docker compose` if docker is the runtime; the Makefile's COMPOSE detection
shows which one the machine has.)

Then provision a scratch tenant the same way the test fixtures do — through
the real API, never raw SQL:

- `POST /api/auth/register` `{email, password}` (unique throwaway email)
- `POST /api/auth/token` (form fields `username`, `password`) → `access_token`
- seed whatever the scenario needs via `POST /api/groups`, `/api/categories`
  (`{name, groupId, keywords}`), `/api/accounts`, `/api/transactions`
  (`{date, amount, accountId, ...}`, kopecks, expenses negative),
  `PUT /api/budgets` (`{categoryId, year, month, amount}`),
  `POST /api/groups/reorder` (`{ids}` — all ids, new order).

The seed data mirrors what the final spec will build with `user.api.*`, so
choose it as if writing the test already (amounts under 1 000 ₽ dodge locale
group separators in assertions).

## Phase 2 — live walkthrough in a visible browser

Use the Playwright MCP browser tools (they open a real, headed Chrome on the
user's machine). Rules of the demonstration:

- Navigate to `http://localhost:8078`, log in through the real login form with
  the scratch user — the user should see the whole journey, including entry.
- Move **slowly and deliberately**: one action, then a short narration in chat
  of what was just done and what should now be visible, then the next action.
  The user is watching the window and will interject with corrections.
- When the user corrects a step, redo it their way and note the correction —
  it becomes part of the recorded scenario.
- Ask the user to call out the checkpoints: every "and here I should see X" is
  an assertion in the future spec. If the user gives none, propose them.
- Keep going until the user says some variant of "record it".

## Phase 3 — codify into a spec

Translate the corrected walkthrough into `web/e2e/<feature>.spec.js`. Read
`web/e2e/README.md` and an existing spec (e.g. `budget.spec.js`) first, then
follow the house rules:

- Import `test`/`expect` from `./fixtures/fixtures.js`, never from
  `@playwright/test` directly. The `user` fixture registers a fresh tenant per
  test — do not reuse the scratch user from the demo.
- Re-create the demo's seed data with `user.api.*` builders; add a missing
  builder to `fixtures.js` rather than calling `request` inline.
- Start with `openApp(page, user)` (pins the clock to FIXED_NOW = 2026-06-15
  and logs in via token). Only auth flows drive the login form itself.
  Navigate with `gotoSection(page, "<Sidebar label>")`.
- Every checkpoint from the demo becomes an `expect(...)`. A spec with no
  assertions is a walkthrough, not a test — do not write it.
- Selector conventions learned the hard way. Mantine SegmentedControl: the
  radio inputs are moved off-viewport — click the label text
  (`page.getByText("Plan", { exact: true })`), never the radio. Kanban
  drag-and-drop is custom pointer-event DnD with a 5px threshold: use stepped
  `page.mouse.move()` calls (see `dragColumn` in `categories.spec.js`), not
  `dragTo`. Prefer the stable BEM-ish classes (`.yg-row`, `.cat-row`, `.gsel`,
  `.kb-col[data-gid]`) and visible text; never nth-child chains on layout.
- Express all dates relative to `FIXED_NOW`/`YEAR`/`MONTH` so the spec
  survives month/year rollover.
- Keep the e2e cap small: one spec = one user journey. Exhaustive coverage
  belongs to engine unit tests and backend integration tests.

## Phase 4 — prove it, then clean up

1. Run the new spec alone against the still-running stack:
   `cd web && npx playwright test e2e/<feature>.spec.js`
2. Offer the user a headed replay (`--headed`) so they see their scenario run
   at full speed.
3. Tear the stack down, then run the full gate exactly as CI will:
   `podman compose -f deploy/docker-compose.test.yml -p monori-e2e down --volumes`
   then `make t-slow`.
4. `make fmt` (prettier) and `cd web && npm run lint` before committing. Note:
   oxlint reads a fixture callback named `use` as a React hook — name it
   `provide` (see fixtures.js).

Only after `make t-slow` is green is the test considered recorded.
