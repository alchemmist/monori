# Quality Graph migration

Issue 424 migrates CI orchestration to `qg.yaml`. The generated
workflows and `.quality-graph/manifest.json` are committed build artifacts and
must not be edited by hand.

## Parity map

| Previous check | Quality Graph node | Implementation |
| --- | --- | --- |
| workflow graph freshness | `workflow-graph` | `qg validate` |
| formatting | `fmt-check` | existing `make fmt-check` |
| triple quotes | `triple-quotes` | `quality-graph-python` |
| lint suppressions | `suppressions` | `quality-graph-python` |
| hardcoded web colors | `hardcoded-colors` | Monori-specific checker |
| documentation links | `docs-links` | existing `make docs-links` |
| lint and generated files | `lint` | existing `make lint` |
| object annotations | `object-annotations` | `quality-graph-python` |
| unsafe type casts | `type-casts` | Monori-specific checker |
| strict typing | `type` | existing `make type` |
| static analysis | `analyze` | existing `make analyze` |
| time bombs | `time-bombs` | `quality-graph-python` |
| fast, medium, and slow tests | `test-*` | existing Make targets |
| flaky tests | `flaky-tests` | Monori discovery and repetition commands |
| frontend build | `build` | existing `make build` |
| total and changed-line coverage | `coverage` | existing `make coverage-diff` |
| changed-line mutation testing | `mutation` | existing `make mutation-diff` |
| bundle regression | `bundle-size` | Monori measurement producer |
| browser performance | `frontend-performance` | existing performance producer |
| dependency and secret audits | `audit` | existing `make audit` |

The scheduled backend, browser, and full-mutation runs remain in their existing
workflows during bootstrap. They are default-branch health and performance jobs,
not pull-request graph nodes.

## Rollout

1. Open the bootstrap pull request with both the legacy and generated workflows enabled.
2. Compare every mapped node on that pull request. Record any intentional difference.
3. Merge the bootstrap without changing branch protection.
4. Open a probe pull request from the updated default branch. This is required because
   trusted publication reads topology from the base branch.
5. Confirm the complete dashboard, commands, approvals, labels, reruns, and fork-safe run.
6. Change branch protection to require only the aggregate `Quality Graph` check.
7. Remove the superseded PR orchestration and its tests. Retain the Make targets and
   Monori-specific producers referenced by `qg.yaml`. Completed after the probe
   pull request confirmed the generated graph and publisher lifecycle.

## Rollback

Before branch protection changes, disable or remove the two generated workflows;
the legacy workflow remains authoritative. After branch protection changes, restore
the legacy required checks first, then disable the generated publisher and runner.
Never remove both required-check paths in the same branch-protection operation.
