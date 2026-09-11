---
name: phase-scope-guard
description: Verify a change during the quant-hub modernization effort (Phase 1 API, Phase 2 frontend, Phase 3 migration) hasn't touched scan-rubric or scoring logic, then re-run the test suite to confirm the pass count is unchanged. Use before committing any Phase 1/2/3 work, or whenever asked to double-check scope on this effort.
---

# Modernization scope guard

`docs/MODERNIZATION_AUDIT.md` lays out a 5-phase plan to decouple the frontend
from Postgres and eventually retire the Streamlit dashboard. The user agreed
to this specifically because they were worried an agent building the API or
frontend might accidentally alter scan-rubric or scoring logic along the way.
That boundary is a hard rule, not a suggestion — treat any violation as a
stop-and-flag situation, not something to quietly work around.

## Forbidden paths

Phase 1/2/3 work must never modify:

- `src/quant_hub/scoring/`
- `src/quant_hub/factors/`
- `src/quant_hub/filters/`
- `src/quant_hub/regime/`
- `src/quant_hub/strategies/`
- `src/quant_hub/engine/`
- `src/quant_hub/lynch/`
- `src/quant_hub/report/`
- any **write** method on a repository class in
  `src/quant_hub/infrastructure/postgres/repository.py` (new read-only
  methods are fine and expected; touching an existing write method, or
  turning a read into something that mutates, is not)

Additive, read-only work belongs in `src/quant_hub/api/`, `frontend/`,
`pyproject.toml` (API deps), and new read methods on the repository classes.

## Before committing

1. **Diff scope check** — compare the changed paths against the forbidden
   list above:

   ```bash
   git diff --stat <base>...HEAD   # or against the working tree if uncommitted
   ```

   If anything under a forbidden path shows up, stop. Don't commit. Explain
   to the user exactly what changed and why it appears to cross the
   boundary — it may be an accidental edit, or it may be a case the user
   needs to explicitly approve as an exception.

2. **Re-run the test suite** — this repo has no CI yet
   (`docs/ARCHITECTURE_GAPS.md` H6), so this is the only regression check:

   ```bash
   docker exec quant-hub-dev pytest -q
   ```

   Confirm the pass count matches the pre-change baseline (no new failures,
   no tests silently removed/skipped). If you don't have a baseline count
   from earlier in the session, run it once before starting the change and
   once after, and compare.

3. **Rubric-focused subset** (faster, run this first when iterating) covers
   the scoring/eligibility logic most directly:

   ```bash
   docker exec quant-hub-dev pytest \
     tests/unit/test_launchpad_rubric.py \
     tests/unit/test_launchpad_ineligible_scores.py \
     tests/unit/test_lynch.py \
     tests/unit/test_lynch_service.py \
     tests/unit/test_ticker_actionable.py \
     -q
   ```

4. **Report back concisely**: paths touched, whether any forbidden path was
   hit, and the before/after test pass count. This is the evidence the user
   is relying on to trust the boundary held — don't skip it even when the
   change feels obviously safe.

## Branch strategy reminder

Each phase merges into `dev` (fast-forward, after this guard passes) before
the next phase branches off `dev` — phases are not stacked on each other.
