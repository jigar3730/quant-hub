---
name: phase-scope-guard
description: Verify a quant-hub change hasn't touched scan-rubric or scoring logic, then re-run the test suite and confirm the pass count didn't drop. Use before committing or merging any feature/phase branch (API, frontend, sector swing, positions, migrations), or whenever asked to double-check scope.
---

# Scope guard

The user's standing worry is that feature work (API, frontend, swing scanner,
etc.) silently alters scoring. That boundary is a hard rule: a violation means
stop and flag, never work around it.

## Forbidden paths (unless the user explicitly asked for that change)

- `src/quant_hub/{scoring,factors,filters,regime,strategies,engine,lynch,report}/`
- existing **write** methods in `src/quant_hub/infrastructure/postgres/repository.py`
  (new read methods are fine)

`.claude/settings.json` makes edits to these paths prompt; this skill is the
check for anything that slipped through (e.g. shell edits).

Note: `src/quant_hub/sector_swing/report.py` is **not** forbidden — only the
top-level `report/` package is.

## Steps

1. **Scope diff** against `main`, covering committed and uncommitted work:

   ```bash
   git diff --name-only main...HEAD; git diff --name-only HEAD; git ls-files -o --exclude-standard
   ```

   Anything under a forbidden path: stop, don't commit, tell the user exactly
   what changed.

2. **Tests**:

   ```bash
   docker exec quant-hub-dev pytest -q
   ```

   Compare against a baseline from the start of the session (or from `main`:
   `git stash -u && docker exec quant-hub-dev pytest -q; git stash pop`).
   No new failures, no tests quietly deleted or skipped.

   Faster rubric subset while iterating:

   ```bash
   docker exec quant-hub-dev pytest -q tests/unit/test_launchpad_rubric.py \
     tests/unit/test_launchpad_ineligible_scores.py tests/unit/test_lynch.py \
     tests/unit/test_lynch_service.py tests/unit/test_ticker_actionable.py
   ```

3. **Frontend** (if `frontend/` changed):
   `docker exec quant-hub-frontend-dev npx tsc -b && docker exec quant-hub-frontend-dev npm run lint`

4. **Report**: paths touched, forbidden-path hits (expect "none"), and the
   before/after pass count. The user relies on this evidence, so include it
   even when the change is obviously safe.

## Branching

Trunk is `main`. Each phase or feature gets one branch off `main` and one
merge/PR back, after this guard passes. The old `dev` branch is stale; don't
branch from it.
