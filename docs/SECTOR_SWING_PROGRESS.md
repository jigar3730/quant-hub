# Sector-ETF Swing Scanner — Progress and Handoff

**Last updated:** 2026-09-20
**Reference docs:** [spec](sector_etf_scanner_spec.md) · [pipeline reference](SECTOR_SWING_SCANNER.md) · [user manual section](USER_MANUAL.md)

## Where things stand

| Phase | What | State |
|---|---|---|
| 1 | Scanner, persistence, CLI, cron, docs | **Done, committed** (`4138d04`), not merged |
| 1b | Streamlit tab | **Dropped** — Streamlit is being decommissioned |
| 1c | React `/swing` page + in-page help | **Done, committed** (`d1bb6ed`), not merged |
| — | Universe: add ARKF, FDIG, ARKG | Committed (`e22b161`), your change; see open questions |
| — | Universe: add SCHG, SCHD (broad growth / dividend ETFs) | Committed 2026-10-07; they compete for the top-4 leader slots like any sector ETF |
| 2 | Paper position tracking | Not started |
| 3 | Backtest and validation | Not started |
| 4 | Command Center / digest / ML integration | Not started — needs explicit approval |

### Branches (nothing pushed, nothing merged)

```text
dev
 └─ feat/sector-swing-scanner   041d81a spec · 4138d04 Phase 1
     └─ feat/sector-swing-react  d1bb6ed React page · e22b161 universe change   <- checked out
```

Merge order: Phase 1 into `dev` first, then the React branch (it contains the Phase 1 commits).

### Environment (dev stack)

- `quant-hub-dev` and `quant-hub-api-dev` were rebuilt from the current code: `quant-sector-swing` is on `PATH`, the crontab has the 05:20 ET weekday line, and the tests are baked in. A second rebuild after the last commits was a no-op (identical image).
- **First automatic cron run: Monday 2026-09-21, 05:20 ET.** Not yet observed.
- Dev DB has one real run: id 197, scan date 2026-09-19, prices as of 2026-09-18, 19 tickers → 0 Tier 1, 1 Tier 2 (ARKG), 18 filtered. The regime gate passed.
- React page: `http://localhost:5020/swing`.

### Verification so far

- Backend: pytest went 185 → 282 passed (97 new sector-swing tests), nothing removed. The 97 sector tests were re-run from the image's own copies.
- Frontend: `tsc -b` clean; lint 0 errors (3 old warnings in `button`, `badge`, `UniverseTable`); production bundle builds; 29 server-render checks pass against the real scan and a synthetic one (trigger / watch / regime-blocked / stale / empty). The TypeScript sizing function matches the Python one on a 180-case grid.
- **Not done: nobody has looked at the page in a real browser.** Do this first tomorrow.
- No forbidden path touched (scoring, factors, filters, regime, strategies, engine, lynch, report, `repository.py` write methods, `indicators.py`, `dashboard/`).

## Decisions already made

- Separate pipeline persisted through the existing `upsert_scan` (no schema change, no API change); rationale is in `SECTOR_SWING_SCANNER.md` §11.
- React only, no Streamlit work.
- No candlestick chart in v1: the API has no price endpoint, so the page draws a price ladder from stored levels.
- Share counts are recomputed in the browser from your own equity and risk % (stored in `localStorage`); the scanner's own share count is a $50,000 / 1% placeholder. The 30% position cap is a constant in `frontend/src/lib/swing.ts`, not in the payload.
- Added beyond the spec: a `signal_cap` filter reason, provenance fields copied into `market_regime` and each ticker's detail (the API doesn't return `data_provenance`), `models.py`, and `quant-hub status` listing sector-swing runs.

## Open questions for you

1. **ARKF / FDIG / ARKG.** ARKF ($5.8M/day) and FDIG ($1.0M/day) fall under the $20M dollar-volume floor and are always "Illiquid", so they add nothing today. ARKG is a real outlier (+93% over 126 days) and now ranks #1, which pushes XLK out of the top-4 leader slots. Keep, drop, or filter thematic funds out of the leader ranking?
2. **Candles.** Add `GET /prices/{ticker}` plus a chart library, or is the ladder enough once you have seen it?
3. **Prod.** `docker-compose.prod.yml` has no frontend service, so `/swing` is dev-only until React is deployed there. The spec says to run in stage for about a week before enabling the cron in prod.

## Suggested next steps

1. Open `/swing` in a browser; note anything confusing (this is where the "user friendly" work should continue).
2. After Monday 05:20 ET: check `docker exec quant-hub-dev quant-hub status` (a `sector-swing-daily` job should show `success`), `tail /app/logs/cron.log` in the container, and `http://localhost:5020/swing`.
3. Merge Phase 1, then the React branch (PRs not opened yet).
4. Decide the three open questions above.
5. Then Phase 2 (paper positions: new `sector_swing_positions` table appended to `schema.sql`, its own repository file, a service and CLI) or Phase 3 (point-in-time backtest reusing the 5-year price cache).

## Known limitations and loose ends

- NYSE holiday list is hard-coded for 2025–2028 (`sector_swing/calendar.py`).
- `docker/jobs.yaml` was already stale (17:xx times); only the sector-swing entry matches `docker/crontab`.
- 15 ruff errors already existed on `dev` in files outside this work (mostly forbidden paths); none are from this feature.
- `data/universes/sector_etfs.txt` ends with a stray blank line (harmless).
- Regime gate is SPY-trend only (no breadth confirmation); Phase 4 integration and open-position awareness are not built.

## Handy commands

```bash
# tests (image has them baked in; src/ is bind-mounted)
docker exec quant-hub-dev pytest -q tests/unit/test_sector_swing_*.py
docker exec quant-hub-dev pytest -q                       # full suite (~2.5 min)

# run the scanner
docker exec quant-hub-dev quant-sector-swing --dry-run
docker exec -e LOG_LEVEL=INFO quant-hub-dev quant-sector-swing --force-refresh
docker exec quant-hub-dev quant-hub status

# frontend checks (do NOT run `npm run build` in the container: it writes root-owned dist/ into the repo)
docker exec quant-hub-frontend-dev npx tsc -b
docker exec quant-hub-frontend-dev npm run lint

# rebuild after changing the Dockerfile, crontab or pyproject scripts
./scripts/run_env.sh dev up -d --build --no-deps quant-hub quant-hub-api
```
