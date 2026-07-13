# REST API

monori exposes a full REST API under `/api`. The web app is just one client of
it — everything the UI does, and more (manual transaction editing, bulk
operations), is available over HTTP.

All money is **integer kopecks** in both directions. All request and response
bodies are JSON. Field names are `camelCase`.

## Authentication

Auth is optional and controlled by the `MONORI_API_TOKEN` environment variable
(see [Configuration](configuration.md)):

- **Unset** — every route is open.
- **Set** — every route, including `GET /api/snapshot`, requires
  `Authorization: Bearer <token>`. A missing or wrong token gets `401`. The
  comparison is constant-time.

```bash
curl -H "Authorization: Bearer $MONORI_API_TOKEN" http://localhost:8000/api/snapshot
```

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
  "groups": [{ "id": 1, "name": "Bills", "sort": 1, "kind": "expense" }],
  "categories": [
    { "id": 1, "groupId": 1, "name": "Rent", "keywords": "rent|landlord",
      "sort": 1, "archived": false }
  ],
  "transactions": [
    { "id": 1, "date": "2026-01-05T00:00:00", "amount": -150000,
      "description": "LANDLORD", "bankCategory": "Housing", "mcc": "6513",
      "categoryId": 1, "comment": "", "source": "import" }
  ],
  "budgets": [{ "categoryId": 1, "year": 2026, "month": 1, "amount": 150000 }]
}
```

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
| DELETE | `/api/categories/{id}` | — | Query `?reassignTo=<id>` moves its transactions first; budgets cascade-delete. |
| POST | `/api/categories/reorder` | `{ids: [...]}` | Must list every category exactly once. |
| POST | `/api/categories/{id}/merge` | `{into: <id>}` | Moves transactions to the target, unions keywords, deletes the source. |

## Transactions

### `GET /api/transactions`

Query parameters (all optional):

| Param | Meaning |
| ------- | --------- |
| `from`, `to` | Inclusive date bounds; compared at day granularity, so `to=2026-01-31` includes that day's timestamps. |
| `categoryId` | Restrict to one category. |
| `uncategorized` | `true` returns only rows with no category (overrides `categoryId`). |
| `q` | Case-insensitive substring match on the description. |
| `limit` | 1–1000, default 100. |
| `offset` | Default 0. |

Returns `{"total": <count>, "rows": [ ...serialized transactions... ]}`, ordered
newest-first (`date DESC, id DESC`).

### Mutations

| Method | Path | Body | Notes |
| -------- | ------ | ------ | ------- |
| POST | `/api/transactions` | `{date, amount, description?, bankCategory?, mcc?, categoryId?, comment?}` | Creates with `source: "manual"`; hash computed server-side. `categoryId` of `0`/`null` means uncategorized; a non-existent id gives `400`. |
| PATCH | `/api/transactions/{id}` | any subset of the create fields | Recomputes the dedup hash from the resulting date/amount/description. |
| DELETE | `/api/transactions/{id}` | — | `404` if missing. |
| POST | `/api/transactions/bulk` | `{action, ids, categoryId?}` | `action` is `categorize`, `move`, or `delete`. Returns `{affected}`. |

`categorize` and `move` are equivalent — both set `categoryId` on every id.

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

### `POST /api/import/preview`

Body `{text}` — the raw statement paste. Parses it, auto-categorizes each row,
and flags duplicates against the database and within the batch.

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

Body `{rows: [...]}` where each row is `{date, amount, description?,
bank_category?, mcc?, categoryId?}`. The server recomputes each hash (never
trusting the client) and inserts only genuinely new rows with `source: "import"`.

```json
{ "inserted": 42, "skipped": 3 }
```

Committing the same batch twice inserts nothing the second time — the operation
is idempotent. See [Importing statements](importing.md) for the dedup rules.

## Interactive docs

Because the backend is FastAPI, the live OpenAPI docs are always available at
`/docs` (Swagger UI) and `/redoc` on a running instance.
