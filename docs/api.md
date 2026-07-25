# REST API

monori exposes a full REST API under `/api`. The web app is just one client of
it — everything the UI does, and more (manual transaction editing, bulk
operations), is available over HTTP.

All money is **integer kopecks** in both directions. All request and response
bodies are JSON. Field names are `camelCase` — with one deliberate exception: the
import endpoints (`/api/import/preview` and `/api/import/commit`) use snake_case
`bank_category` in their row objects, matching the parsed statement shape. This
is called out again in the [Import](#import) section.

## Authentication

monori is multi-user: people register, sign in, and each sees only their own
budget. Every data route requires a bearer JWT; only the auth endpoints, this
docs site, and the OpenAPI helpers (`/api-docs`, `/api-redoc`, `/openapi.json`)
are public.

- **`POST /api/auth/register`** — body `{email, password}` (password ≥ 8 chars).
  Creates a user (Argon2-hashed password) and returns `{id, email, createdAt}`.
  `409` if the email is already registered, `400` on a bad email/short password.
  A new user starts with a default **Cash** account. The **first** user to
  register also claims any data that predates multi-user (see
  [Data model](data-model.md)).
- **`POST /api/auth/token`** — OAuth2 password grant (form-encoded `username` =
  email, `password`). Returns `{access_token, token_type: "bearer"}` — a JWT
  valid for 7 days — or `401`. The failure `detail` names the field at fault:
  `no account is registered for this email` vs `incorrect password`, so the
  sign-in form can point at it. This trades away enumeration resistance — the
  endpoint confirms which addresses are registered.
- **`PATCH /api/auth/me`** — body `{baseCurrency}` changes the reporting
  currency (see [Currencies](currencies.md)).
- **`GET /api/auth/me`** — with `Authorization: Bearer <access_token>`, returns
  the current user; `401` if the token is missing, malformed, or expired.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token \
  -d 'username=you@example.com&password=...' | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/snapshot
```

All routes below are scoped to the authenticated user: they see and mutate only
that user's accounts, groups, categories, transactions, budgets, and
connections. A row that belongs to someone else answers `404`. The legacy
`MONORI_API_TOKEN` instance-wide guard is retired.

## Conventions

- Create endpoints return `{"id": <new id>}`.
- Update/delete endpoints return `{"ok": true}`.
- Validation failures from the schema return `422`; semantic conflicts return
  `400`, `404`, or `409` with a `detail` message.

## Snapshot

### `GET /api/snapshot`

Returns the entire state in one call — the frontend loads this on startup.

```json
{
  "accounts": [
    { "id": 1, "name": "T-Bank", "type": "card", "icon": "wallet",
      "color": "#5b6472", "iconImage": null, "currency": "RUB", "sort": 1,
      "archived": false, "openingBalance": 0, "openingDate": null }
  ],
  "groups": [{ "id": 1, "name": "Bills", "sort": 1, "kind": "expense" }],
  "categories": [
    { "id": 1, "groupId": 1, "name": "Rent", "keywords": "rent|landlord",
      "sort": 1, "archived": false }
  ],
  "transactions": [
    { "id": 1, "date": "2026-01-05T00:00:00", "amount": -150000,
      "currency": "RUB", "baseAmount": -150000,
      "description": "LANDLORD", "bankCategory": "Housing", "mcc": "6513",
      "categoryId": 1, "accountId": 1, "transferId": null, "comment": "",
      "source": "import" }
  ],
  "budgets": [{ "categoryId": 1, "year": 2026, "month": 1, "amount": 150000 }],
  "transfers": [],
  "transactionsTotal": 1,
  "baseCurrency": "RUB",
  "rates": [
    { "code": "RUB", "rate": 1.0, "day": "2026-07-25", "source": "pivot", "stale": false },
    { "code": "GEL", "rate": 30.4, "day": "2026-07-25", "source": "cbr", "stale": false }
  ]
}
```

`amount` is in `currency`; `baseAmount` is the same money in `baseCurrency`, at
the rate for the transaction's date. Only `baseAmount` may be summed across
accounts. `rates` are rubles per unit, enough for a client to convert the money
that has no transaction behind it (opening balances). See
[Currencies](currencies.md).

Query parameters:

| Param | Meaning |
| ------- | --------- |
| `light` | `1` caps `transactions` at the newest `limit` rows, still in canonical `date, id` order. Everything else — accounts, groups, categories, budgets, connections — stays complete. |
| `limit` | Size of that window: 1–5000, default 500. Validated whenever it is present, but only has an effect together with `light`. |

`transactionsTotal` always reports the full transaction count, so a client can
tell how much of the ledger it holds. The frontend requests `?light=1` for a
fast first paint and then fills the rest in the background over
`GET /api/transactions` with `limit`/`offset`, merging each chunk into the
canonical order.

## Accounts

Where transactions live: cards, cash, savings. `type` is one of `card`, `cash`,
`savings`, `other`. `currency` is what money on the account is held in: new
transactions inherit it, and the balance is reported in it. An account's balance
is `openingBalance` plus the sum of its transactions. An unknown currency code
gives `400`.

| Method | Path | Body | Notes |
| -------- | ------ | ------ | ------- |
| GET | `/api/accounts` | — | List, ordered by `sort`. |
| POST | `/api/accounts` | `{name, type?, icon?, color?, iconImage?, currency?, openingBalance?, openingDate?}` | `409` duplicate name, `400` bad type/color/image. `color` is `#rrggbb`; `iconImage` is an image data URL (size-capped) that overrides the glyph. |
| PATCH | `/api/accounts/{id}` | `{name?, type?, icon?, color?, iconImage?, currency?, openingBalance?, openingDate?, archived?}` | Partial update. `iconImage: ""` clears the custom image back to the glyph. |
| DELETE | `/api/accounts/{id}` | — | Query `?reassignTo=<id>` moves its transactions first. A non-empty account without a target, or the last account, gives `400`. |
| POST | `/api/accounts/reorder` | `{ids: [...]}` | Must list every account exactly once. |
| POST | `/api/accounts/{id}/reconcile` | `{actualBalance}` | Posts an `adjustment` transaction for `actualBalance − computed balance`. Returns `{delta}` (`0` when already matching). |

## Transfers

A transfer is an entity over two transactions — a negative leg on the source
account, a positive leg on the destination — that both carry its `transferId`.
The transactions themselves stay ordinary rows with their own ids and dedup
hashes, so a re-sync still recognizes them and cannot duplicate them. Both legs
are uncategorized while merged, so transfers never count as income or expense.

| Method | Path | Body | Notes |
| -------- | ------ | ------ | ------- |
| GET | `/api/transfers` | — | `{rows: [{id, outTxId, inTxId, origin, note, createdAt}]}`. `origin` is `manual` (created here or by the dialog) or `matched` (found by detection). |
| POST | `/api/transfers` | `{fromAccountId, toAccountId, amount, toAmount?, date, comment?}` | Creates both legs and merges them. `amount` must be positive; the two accounts must differ. Each leg is denominated in its own account's currency; when those differ, `toAmount` says what actually arrived, and without it the day's rate decides. Returns `{transferId}`. |
| POST | `/api/transfers/link` | `{outTxId, inTxId, note?}` | Merges a pair already in the ledger. `400` unless the legs are one outflow and one inflow on two different accounts, neither already in a transfer. The amounts need not match — the caller is the user, who knows about fees. Returns `{transferId}`. |
| DELETE | `/api/transfers/{transferId}` | — | **Splits** the transfer: both transactions stay and get their pre-merge categories back. Deleting the money means deleting the two rows afterwards. `404` if unknown. |
| GET | `/api/transfers/suggestions` | `?maxDays=5` | Pairs detection found but would not merge unasked: `{rows: [{outTxId, inTxId, amount, days, hint}], transactions: [...]}`. |
| POST | `/api/transfers/suggestions/dismiss` | `{outTxId, inTxId}` | Remembers that this pair is not a transfer, so it is never offered again. |
| POST | `/api/transfers/detect` | `?maxDays=5` | Scans the ledger, merges the unambiguous pairs and counts the rest. Returns `{merged: [...], suggested}`. Runs automatically after every import and bank sync. |

### How a pair is detected

A candidate is an outflow and an inflow that sit on two different accounts of
the same user, have **exactly** opposite amounts in the same currency, fall within `maxDays` of each
other, are both unattached, and have not been dismissed. Candidates are matched
greedily closest-first, and each transaction is used at most once, so the result
does not depend on row order. Pairs a day or less apart are merged outright;
anything looser becomes a suggestion. Unequal amounts (a transfer fee) never
match automatically — link those by hand.

## Groups

`kind` is `"income"` or `"expense"`.

| Method | Path | Body | Notes |
| -------- | ------ | ------ | ------- |
| GET | `/api/groups` | — | List, ordered by `sort`. |
| POST | `/api/groups` | `{name, kind}` | `409` on duplicate name, `400` on bad kind. |
| PATCH | `/api/groups/{id}` | `{name?, kind?}` | `404` if missing, `409` on name clash. |
| DELETE | `/api/groups/{id}` | — | `409` if the group still has categories. |
| POST | `/api/groups/reorder` | `{ids: [...]}` | `ids` must list every group exactly once. |

## Categories

`keywords` is a pipe-separated string (`"coffee|cafe|espresso"`) used by the
importer.

| Method | Path | Body | Notes |
| -------- | ------ | ------ | ------- |
| POST | `/api/categories` | `{name, groupId, keywords?}` | `400` unknown group, `409` duplicate name. |
| PATCH | `/api/categories/{id}` | `{name?, groupId?, keywords?, archived?}` | Partial update. |
| DELETE | `/api/categories/{id}` | — | Leaves its transactions uncategorized; budgets cascade-delete. To move them somewhere instead, use `/merge`. |
| POST | `/api/categories/reorder` | `{ids: [...]}` | Must list every category exactly once. |
| POST | `/api/categories/{id}/merge` | `{into: <id>}` | Moves transactions to the target, unions keywords, sums budgets month by month, deletes the source. `400` when the two sit in groups of a different kind. |

## Transactions

### `GET /api/transactions`

Query parameters (all optional):

| Param | Meaning |
| ------- | --------- |
| `from`, `to` | Inclusive date bounds; compared at day granularity, so `to=2026-01-31` includes that day's timestamps. |
| `categoryId` | Restrict to one category. |
| `accountId` | Restrict to one account. |
| `uncategorized` | `true` returns only rows with no category (overrides `categoryId`). |
| `q` | Case-insensitive substring match on the description. |
| `limit` | 1–1000, default 100. |
| `offset` | Default 0. |

Returns `{"total": <count>, "rows": [ ...serialized transactions... ]}`, ordered
newest-first (`date DESC, id DESC`).

### Mutations

| Method | Path | Body | Notes |
| -------- | ------ | ------ | ------- |
| POST | `/api/transactions` | `{date, amount, accountId, currency?, description?, bankCategory?, mcc?, categoryId?, comment?}` | Creates with `source: "manual"`; hash and `baseAmount` computed server-side. `accountId` is required and must exist. `currency` defaults to the account's; an unknown code gives `400`. `categoryId` of `0`/`null` means uncategorized; a non-existent id gives `400`. |
| PATCH | `/api/transactions/{id}` | any subset of the create fields (`accountId` moves the row to another account) | Recomputes the dedup hash and `baseAmount`. Moving a row to another account does **not** re-denominate it — pass `currency` to change that deliberately. |
| DELETE | `/api/transactions/{id}` | — | `404` if missing. |
| POST | `/api/transactions/bulk` | `{action, ids, categoryId?}` | `action` is `categorize`, `move`, or `delete`. Returns `{affected}`. |

`categorize` and `move` are equivalent — both set `categoryId` on every id.

## Currencies and rates

Rates are quoted in **rubles per unit** and stored per day, so any conversion is
two lookups. Every write here changes what stored transactions are worth, so
each one reprices the caller's ledger before answering and reports how many rows
moved. See [Currencies](currencies.md).

| Method | Path | Body | Notes |
| -------- | ------ | ------ | ------- |
| GET | `/api/rates` | `?day=YYYY-MM-DD` | `{day, baseCurrency, currencies: [{code, name, symbol, minorUnits}], rates: [{code, rate, day, source, stale}]}`. `day` on a rate is when it was actually published; `stale` says it is older than the day asked for. `source` is `pivot`, `cbr`, `manual` or `bundled`. |
| POST | `/api/rates/refresh` | `?days=0` | Fetches today from the Bank of Russia, plus the last `days` (0–90) of any days with nothing stored. Returns `{stored, days, repriced}`. `502` if the feed is unreachable. |
| PUT | `/api/rates/{code}` | `{rubPerUnit, day?}` | Sets a rate by hand for `day` (today by default). `400` for an unknown code or for `RUB`, which is the pivot and is always 1. Returns `{code, day, repriced}`. |
| PATCH | `/api/auth/me` | `{baseCurrency?}` | Changes the reporting currency and reprices every transaction at the rate for its own date. Returns `{user, repriced}`. `400` for an unknown code. |

## Budgets

A budget cell is `{categoryId, year, month, amount}`. Setting `amount` to `0`
deletes the cell.

| Method | Path | Body | Returns |
| -------- | ------ | ------ | --------- |
| PUT | `/api/budgets` | one cell | `{ok: true}` |
| POST | `/api/budgets/bulk` | `{cells: [...]}` | `{set: <count>}` |
| POST | `/api/budgets/copy` | `{fromYear, toYear, fromMonth?, toMonth?}` | `{copied: <count>}` |

`copy` works in two modes: give **both** `fromMonth` and `toMonth` to copy a
single month, or **neither** to copy a whole year. The destination scope is
cleared first, so it becomes an exact copy of the source (anything else is a
`400`).

## Import

> The import row objects use snake_case `bank_category` (not `bankCategory`),
> unlike the rest of the API — they mirror the parsed statement shape.

### `POST /api/import/preview`

Body `{text}` — the raw statement paste. Parses it, auto-categorizes each row,
and flags rows already covered by the database as duplicates.

```json
{
  "rows": [
    { "date": "2026-01-05T12:30:00", "amount": -45000, "description": "COFFEE",
      "bank_category": "Cafes", "mcc": "5814", "hash": "…",
      "categoryId": 3, "duplicate": false }
  ],
  "errors": [{ "line": 7, "error": "unparseable date or amount", "raw": "…" }]
}
```

### `POST /api/import/commit`

Body `{accountId, rows: [...]}` where each row is `{date, amount, description?,
bank_category?, mcc?, categoryId?}`. `accountId` targets the whole batch — every
imported row lands on that account. The server recomputes each hash (never
trusting the client) and skips only as many occurrences of a hash as the database
already holds, inserting the rest with `source: "import"`.

```json
{ "inserted": 42, "skipped": 3, "transfersMerged": 1, "transfersSuggested": 2 }
```

The commit also runs transfer detection over the ledger, so a statement that
carries both legs of a transfer arrives already merged; `transfersMerged` counts
what it linked and `transfersSuggested` what it left for the user to confirm.

Committing the same batch twice inserts nothing the second time — the operation
is idempotent. See [Importing statements](importing.md) for the dedup rules.

## Connections

A connection is **one bank login owned by the user**; any number of accounts
link to it (`PATCH /api/accounts/{id}` with `{connectionId, bankRef}` — pass
`connectionId: 0` to unlink). A sync logs in once and pulls every linked
account in turn, each landing as its own batch. The routes that handle
secrets — create, update, sync and SMS — require `MONORI_ENCRYPTION_KEY` to be
set (credentials and the cached session are stored encrypted) and return `400`
without it; delete and cancel do not need the key. Connections also appear in
the snapshot as `connections[]`, never carrying any secret material. See
[Configuration → Bank sync connectors](configuration.md#bank-sync-connectors).

### `GET /api/connections/available`

The connectors offered in the bank picker, each with its declared form fields:

```json
[{ "bank": "tbank", "kind": "playwright", "label": "T-Bank (browser sync)",
   "connectionParams": [{ "name": "phone", "label": "Phone", "secret": false, "required": true },
                        { "name": "password", "label": "Password", "secret": true, "required": true }],
   "accountParams": [{ "name": "account", "label": "T-Bank account number (optional)", "required": false }] }]
```

`connectionParams` describe the per-login credentials; `accountParams` describe
the per-account locator stored as the account's `bankRef`.

### `POST /api/connections`

Body `{bank, kind, credentials: {…}}` — the credential keys are the connector's
declared `connectionParams`; missing required fields answer `400`. Creates a
connection in the `disconnected` state and returns it (without secrets). Link
accounts to it afterwards via `PATCH /api/accounts/{id}`.

### `PATCH /api/connections/{id}`

Body `{credentials: {…}}` — replaces the stored credentials and clears the
cached session.

### `DELETE /api/connections/{id}`

Removes the connection and unlinks its accounts (they stay, as manual
accounts). Returns `{deleted: id}`.

### `POST /api/connections/{id}/sync`

Runs a sync now over every linked account (`400` if none are linked). If login
needs an OTP the response is `{"status": "awaiting_sms"}` and the connection
moves to `awaiting_sms`; otherwise each account's rows are committed as their
own batch (`source: "sync"`) and the response summarizes the run:

```json
{ "status": "connected", "inserted": 12, "skipped": 3,
  "accounts": [{ "accountId": 1, "inserted": 8, "skipped": 2, "batchId": 8,
                 "dateFrom": "2026-02-01T09:00:00", "dateTo": "2026-02-14T18:20:00" }],
  "dateFrom": "2026-02-01T09:00:00", "dateTo": "2026-02-14T18:20:00" }
```

### `POST /api/connections/{id}/sms`

Body `{code}` — supplies the OTP for a sync that returned `awaiting_sms`. The
code completes the parked account's pull and the remaining linked accounts
follow on the now-cached session; returns the same summary as `/sync`. Returns
`409` if no login is awaiting a code.

### `POST /api/connections/{id}/cancel`

Abandons a login parked at the OTP step: closes the connector (releasing its
browser session) and drops the connection out of `awaiting_sms`. Called when the
user closes the dialog mid-verification.

## Interactive docs

Because the backend is FastAPI, live OpenAPI docs ship with every instance:
Swagger UI at `/api-docs`, ReDoc at `/api-redoc`, and the raw schema at
`/openapi.json`. (The `/docs` path serves this documentation site instead.)
