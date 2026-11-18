# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```text
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 5. Pull Request Review Protocol

**Every review thread needs an audit trail before handoff.**

- Relevant finding: fix it in a commit, verify the fix, then resolve the thread.
- Irrelevant, duplicate, stale, or false finding: reply in that thread with the concrete reason it does not apply, then resolve it.
- Never resolve a rejected finding silently. A resolved thread without a reply is incomplete review work.
- Re-check all threads after the final bot reviews. Handoff requires zero unresolved threads.
- Treat bot check status and bot review publication as separate signals. Confirm the review's `commit_id` matches the final head; a neutral/skipped check can still accompany a completed review, while a rate-limited reply is not a completed review.
- Add the human reviewer only after the final head is mergeable, the Quality Graph is green, required bot reviews are complete or explicitly waived by the user, and all threads are resolved with the protocol above.
- Do not merge as part of review preparation unless the user explicitly asks.

## 6. Quality Graph Operations

**Use the aggregate result, not a collection of apparently green jobs.**

- Quality Graph result artifacts are attempt-scoped. A `rerun --failed` can produce one new-attempt artifact while leaving every successful node on an older attempt; the publisher then reports missing artifacts. When artifact attempts diverge, run one complete workflow attempt so every node publishes under the same attempt number.
- After a rerun, wait for the publisher and verify the aggregate `Quality Graph` check itself is `SUCCESS`.
- For Coverage failures, distinguish the diff-cover command exits from the report verdict. The report also enforces full coverage of changed executable branches and total-coverage regression; inspect the generated findings instead of lowering coverage thresholds.
- Python dependency audit must export external runtime dependencies with `uv export --no-emit-workspace`; local workspace packages are not PyPI audit targets. Vulnerable external packages still require a lockfile update.
- Frontend performance compares production stacks. Re-run an isolated network or Lighthouse flake before changing policy. Calibrate a noise floor only after repeated identical-run evidence, and preserve relative and poor-band regressions.
- Mutation diff gates are score gates. Do not add a hidden zero-survivor condition beside a numeric threshold; equivalent mutants otherwise make the configured threshold meaningless. The current 60% diff threshold is the measured initial baseline and should rise only with supporting tests.

## 7. Refund Domain Invariants

**A refund is a positive transaction linked to one negative purchase; a purchase may have several partial refunds.**

- `refund_tx_id` is unique; `original_tx_id` is intentionally non-unique for partial refunds.
- The sum of linked refunds cannot exceed the purchase magnitude. Relinking is an explicit supported action and recalculates capacity while excluding the refund being moved.
- Linked refunds use the original purchase's expense category. Changing a purchase category propagates to linked refunds, and optimistic client rollback restores every affected category.
- Import preview may offer expense categories for positive rows because the refund link does not exist yet; ordinary income categories must remain available.
- Analytics and budgets aggregate signed category amounts, so a positive refund in the purchase category nets the expense exactly.
- The UI provides a same-merchant/amount/date import hint and clickable refund badges that navigate to the counterpart transaction.
- Keep demo-mode validation aligned with the server, including sign, date, transfer, split, and remaining-refund-cap checks.
