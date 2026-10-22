-- Per-universe edge of setups (Tier 1-3) vs the same universe, over NON-overlapping windows.
-- Usage: psql -v strategy=launchpad -v horizon=10 -f universe_edge.sql
-- Each run's spread = setup mean fwd return - universe mean fwd return. Runs are averaged
-- per ISO week, then only every k-th week is kept (k = ceil(horizon / 5)) so the forward
-- windows don't overlap. t-stat is over those weeks. Gross of costs.
with o as (
  select r.id run_id, r.universe_id, r.scan_date, t.tier, o.forward_return_pct fwd
  from signal_outcomes o
  join scan_runs r on r.id = o.run_id
  join ticker_results t on t.run_id = o.run_id and t.ticker = o.ticker
  where r.strategy_id = :'strategy' and o.horizon_days = :horizon
    and o.label_status = 'ok' and o.forward_return_pct is not null
), per_run as (
  select run_id, universe_id, min(scan_date) scan_date,
         avg(fwd) filter (where tier in ('Tier 1', 'Tier 2', 'Tier 3')) - avg(fwd) spread,
         count(*) filter (where tier in ('Tier 1', 'Tier 2', 'Tier 3')) setups
  from o group by run_id, universe_id
), per_week as (
  select universe_id, date_trunc('week', scan_date) wk, avg(spread) spread, sum(setups) setups
  from per_run where setups > 0 group by 1, 2
), sampled as (
  select *, dense_rank() over (partition by universe_id order by wk) - 1 idx from per_week
)
select universe_id,
       count(*)                          indep_weeks,
       sum(setups)                       setups,
       round(avg(spread)::numeric, 2)    mean_spread_pct,
       round((avg(spread) / nullif(stddev_samp(spread) / sqrt(count(*)), 0))::numeric, 2) t_over_weeks
from sampled
where idx % ceil(:horizon / 5.0)::int = 0
group by universe_id order by universe_id;
