# Development

## Tech stack

**Frontend** (`web/`)

- React 19 + Vite 8, built on [Gravity UI](https://gravity-ui.com/) (UIKit +
  charts).
- [Zustand](https://github.com/pmndrs/zustand) for state, with optimistic updates.
- The budgeting and analytics math lives in `web/src/engine/` as pure functions,
  unit-tested in isolation.
- Docked side panels use the shared `web/src/ui/Tab.jsx`. Which tabs are open,
  whether each is collapsed and how wide the user dragged it is persisted to
  `localStorage` by `web/src/ui/tabPersist.js`, so a reload restores the stack —
  a tab gets that for free and its props must therefore be JSON-serializable
  (pass ids, not objects with callbacks). Any tab can be resized by dragging its
  left edge, between 10% and 90% of the viewport; a double-click on the edge
  restores the width the tab asks for itself.
- Lint with Oxlint, format with Prettier, style-check with Stylelint, test with
  Vitest, mutation-test with Stryker.

**Backend** (`server/`)

- FastAPI on Python 3.12, managed with [`uv`](https://docs.astral.sh/uv/).
- A thin `main.py` mounts five routers (`groups`, `categories`, `transactions`,
  `budgets`, `imports`) plus `/api/snapshot`, and serves the built SPA from
  `server/static` when present.
- SQLite via the stdlib `sqlite3`; the schema is in `server/app/db.py`.
- Lint/format with Ruff, type-check with mypy, security-scan with bandit +
  semgrep, test with pytest, mutation-test with mutmut.

## Everything runs through `make`

The whole toolchain is exposed as `make` targets, and CI runs those same targets
one-to-one — there is no separate CI script to drift out of sync.

### Run

| Target                  | Does                                                        |
| ----------------------- | ----------------------------------------------------------- |
| `make up` / `make down` | Dev stack in Docker (web on 5173, api on 8077), hot-reload. |
| `make api`              | API only: `uvicorn --reload` on `API_PORT` (default 8077).  |
| `make web`              | Web dev server only, proxying the API.                      |
| `make build`            | `vite build`, then copy `web/dist` into `server/static`.    |

### Format & lint

| Target                | Does                                                                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `make fmt`            | Prettier + Ruff format/fix, and regenerates the schema diagram.                                                                      |
| `make fmt-check`      | The same, check-only.                                                                                                                |
| `make lint`           | Everything: web (Oxlint), CSS, HTML, server (Ruff), YAML, Markdown, generated docs, GitHub Actions, Dockerfile, shell, and spelling. |
| `make schema-diagram` | Regenerates the ER diagram in [data-model.md](data-model.md) from `server/schema.sql`. `make lint` fails if it is stale.             |
| `make typecheck`      | Strict mypy for all tracked Python plus TypeScript compiler and type-aware Oxlint checks.                                           |
| `make analyze`        | bandit + semgrep security scan.                                                                                                      |
| `make audit`          | Dependency + secret scanning (`audit-deps`, `audit-deps-py`, `audit-secrets`).                                                       |

Pull requests also run a CI-only Python annotation gate. It rejects new uses of
`object` as an annotation, including nested types such as `list[object]`. Use a
specific type, a protocol, or a suitable generic instead. If a boundary truly
requires `object`, a repository administrator can approve that finding for the
current commit by posting a new pull request comment containing only
one of `/ignore-object <finding-id>`, `/ignore-file path/to/file.py`, or
`/ignore-all`. An administrator can remove one approval with
`/remove-ignore <finding-id>`. The approval expires when the pull request receives
a new commit.

### Test

The suite is a testing "trophy" — heavy on integration tests that use real
dependencies (a real temp SQLite database, the real FastAPI app), not mocks.

| Target          | Does                                                                                                                                           |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `make test`     | The whole suite (`t-fast` + `t-medium` + `t-slow`).                                                                                            |
| `make t-fast`   | Unit tests: Vitest + pytest `-m "not integration"`.                                                                                            |
| `make t-medium` | Integration tests: pytest `-m integration` against a real DB.                                                                                  |
| `make t-slow`   | Placeholder for end-to-end (Playwright), not yet wired up.                                                                                     |
| `make coverage` | Coverage as a tree (root → back/front → module → file), via `scripts/coverage-tree.sh`. Fails below **90% statements and lines** in `web/src`. |
| `make mutation` | Mutation testing: Stryker on `web/src/engine`, mutmut on `server/app`.                                                                         |

### The pre-commit gate

```bash
make check   # fmt-check + lint + typecheck + analyze + test
```

## Typing policy

All tracked Python is checked with `mypy --strict` and Ruff annotation rules.
Do not introduce `Any`, bare collections, untyped public functions, or broad
per-file ignores. When a third-party API is dynamic, accept it at a small
adapter boundary as `object` and narrow it before it reaches application code.

The frontend uses strict TypeScript and type-aware Oxlint. Use `unknown` for
untrusted JSON and narrow it; do not use `any`, `@ts-ignore`, or `@ts-nocheck`.
An `@ts-expect-error` is only acceptable for a documented, specific third-party
typing defect and must be removed when the upstream types are fixed.

CI runs each of these leaf targets as its own separate check, so a red pipeline
points straight at the failing tool.

## Tests

- Backend integration tests use a fixture that spins up a temp SQLite file and a
  FastAPI `TestClient`, split by resource under `server/tests/integration/`; unit
  tests (e.g. the importer) live under `server/tests/unit/`.
- Coverage is gated: pytest fails under 80% on the backend, and Vitest holds
  `web/src` at 90% statements and lines, with the engine held to the same bar.
- Mutation scores are the real quality check on the test suite; some surviving
  mutants are equivalent (e.g. SQLite's case-insensitive comparisons) and are not
  worth chasing.

## Conventions

- **No code comments** unless a reader genuinely needs one — the code and these
  docs carry the explanation.
- Commit messages are single-line, lowercase, English.
- Feature work starts from an issue; the branch is named after the issue number;
  changes land through a PR.
