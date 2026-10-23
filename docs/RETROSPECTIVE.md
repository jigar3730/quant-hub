# quant-hub retrospective (2026-06-28 → 2026-10-22)

Outcome: **no edge found; development stopped** ([research/CONCLUSION.md](research/CONCLUSION.md)).
This file captures what to keep, what to avoid, and how to start the next project.

## By the numbers

- ~4 months, 120 commits, ~18k lines Python, ~3k lines TypeScript, ~6.9k lines across 24 docs.
- Commits touching UI/dashboard: ~25. Commits touching research/labels/evaluation: ~13.
- **The first real test of whether any strategy works came on day ~116** (2026-10-22). It took
  one day to run and killed both strategies.

That last line is the whole lesson. Everything below elaborates on it.

## What did not work

### 1. Product before proof (the root cause)
We built a scanner, three strategies, Postgres schema, a FastAPI, a React UI with heatmaps,
ticker comparison and score drawers, digest emails, an ML pipeline, multi-environment Docker,
and 24 docs — all on top of rubrics that had never been tested against forward returns. The
UI made the signals *feel* real (tiers, "actionable" badges), which delayed the question
"does this predict anything?".

### 2. Hand-designed rubrics with arbitrary weights
Launchpad's squeeze 40 / volume 30 / tightness 15 / trend 15 + MACD gate came from trading
folklore, not data. Tier 1 needed score ≥ 80 *and* a MACD zero-line cross — conditions that
almost never co-occur, so the headline tier never fired. Result: rank IC ≈ 0 at every
horizon; the "best" tiers underperformed their own universe.

### 3. Crowded hypothesis space
Daily-bar chart patterns on liquid US large/mid caps are the most-watched signals in retail
trading. Prior probability of edge was low; nothing we found moved it.

### 4. Data that can't answer the question
Free Yahoo data, today's index members (survivorship), Lynch fundamentals not point-in-time,
no transaction costs. Several of these were known early and documented, but the work went
ahead anyway.

### 5. Early results that looked like edge
- 6 weeks of live scans showed Tier 3 +1.0% vs universe at h=20, **t 4.1**. It was one regime,
  overlapping windows, and contaminated by bad labels. The 4.5-year test reversed it.
- The best design-period candidate (+5.4% at h=63, t 1.94) flipped to −5.2% on holdout.
- One ticker (PATH) doing well for two days. Noise.
A t-stat on overlapping windows or a handful of dates is not evidence.

### 6. Silent data bugs
Found only when someone finally looked at results:
- Price cache reused yesterday's bars on 12 of 37 days (≈ half of most_actives scored stale).
- Sparse price history produced fake "20-day" returns spanning years (BMNR +1,630%; ~10k bad labels).
- An unescaped `%` in the crontab silently killed weekly ML labeling.
Without an evaluation loop, broken data looks exactly like working data.

### 7. Documentation sprawl
24 docs (several overlapping: ML_OPS / ML_OPERATIONS / ML_FOUNDATION / ML_PROJECTS; multiple
learning/walkthrough guides) for a system with no validated signal.

## What worked (keep these)

### Research method
- **Pre-registration** (`docs/research/LOG.md`, PR-1/PR-2): write the hypothesis and pass rule
  *before* viewing data; count every candidate as a test; log failures.
- **Design / holdout split**, holdout viewed once, after freezing the candidate.
- **Point-in-time backfill**: replay the scanner as of each past date from cached prices,
  then label forward returns. One day of compute answered four months of questions.
- **Measure relative to the same universe on the same date** (removes market beta and most
  survivorship drift), **rank IC per run**, **t-stats over non-overlapping runs**,
  **per-run winsorizing** so one meme spike can't make a mean.
- **"Inconclusive" threshold**: under ~30 independent dates or ~100 signals, don't conclude.
- **Kill fast**: the swing backtest was clearly negative (CAGR −0.45% vs SPY 11.1%) and was
  retired without a sensitivity grid — tuning a loser is curve-fitting.

### Engineering
- Everything in Docker via one wrapper (`scripts/run_env.sh`); bind-mounted src for live edits.
- Postgres as the system of record for scans + labels made the evidence queries trivial.
- Parquet price cache with freshness checks against the NYSE calendar.
- Read-only API + separate frontend: clean, and the read-only DB role pattern is reusable.

### Working with Claude Code
- `CLAUDE.md` with hard rules (protected scoring paths, no fabricated trading numbers,
  never read `.env*`), enforced by `.claude/settings.json` ask/deny permissions.
- Skills that encode procedure: `signal-eval` (how to measure edge), `phase-scope-guard`
  (did scoring change?), `dev-stack`.
- A read-only adversarial subagent (`quant-skeptic`) for any "this works" claim.
- PostToolUse ruff hook catching lint at edit time.
- Standing autonomy authorization with explicit stop gates (scoring, trading levels, prod,
  money).

## Foundation for the next project

### Order of work (non-negotiable)
1. **Hypothesis first.** One sentence, with a published or economic reason it should exist
   (risk premium, behavioral bias, capacity constraint). Not "this pattern looks good".
2. **Data audit.** Can this data answer it? Point-in-time? Delisted names included? Long
   enough to cover ≥ 2 regimes? If not, buy better data or pick another hypothesis.
3. **Pre-register** the pass rule in `LOG.md`: metric, horizon, holdout dates, t threshold,
   cost assumption, max number of candidates.
4. **Evaluation harness before strategy code**: backfill → labels → IC / spread vs universe
   → non-overlapping t → after costs. Test it on a known-good factor (e.g. 12-1 momentum)
   and a known-null (random score) so you know it can detect both.
5. **Run once on holdout.** Skeptic review. Log it.
6. **Only then** build delivery: scheduling, alerts, UI. Smallest possible — a CSV or one
   email beats a dashboard until edge is proven live for ≥ 3 months.

### Rules of thumb
- Budget: no more than ~20% of effort on anything that isn't measuring edge until a signal
  passes holdout.
- Every scheduled job needs a check that it produced output (the `%` bug failed silently).
- Labels get sanity checks: max plausible return, calendar gap between anchor and exit.
- Results are reported net of costs, relative to a benchmark that's free to hold (SPY / index fund).
- One doc per concern; delete docs that describe unvalidated features.

### Candidate hypotheses worth testing (if resuming)
Ordered by evidence strength; all need survivorship-free data (e.g. Norgate) except the first.
1. Time-series trend on ETFs / asset classes (free Yahoo data is adequate; expect drawdown
   reduction more than excess return).
2. Cross-sectional 12-1 momentum on stocks (the only factor with any life in our data).
3. Post-earnings announcement drift (needs earnings dates + surprise data).
Realistic target: a few %/yr over the index after costs, with multi-year dry spells.
If that isn't worth the effort, the index fund is the answer.

### Reusable starter kit from this repo
Copy into the next project and adapt:
- `CLAUDE.md` sections: Hard rules, Research integrity, Verify.
- `.claude/settings.json` (permissions + ruff hook), `.claude/hooks/ruff-check.sh`.
- `.claude/skills/signal-eval/`, `.claude/agents/quant-skeptic.md`.
- `docs/research/LOG.md` structure (results table + pre-registered decisions).
- `src/quant_hub/research/launchpad_factors.py` (run-level IC, non-overlapping t, splits) —
  generalize the panel loader.
- `src/quant_hub/data/calendar.py`, `infrastructure/cache/parquet_cache.py`,
  `ml/labels.py` (with the `price_gap` guard).
