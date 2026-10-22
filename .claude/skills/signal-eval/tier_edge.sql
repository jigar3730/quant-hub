-- Per-tier edge vs the same universe on the same date, aggregated over dates.
-- Usage: psql -v strategy=launchpad -v horizon=20 -f tier_edge.sql
-- spread = tier mean fwd return - universe mean fwd return, per run (date x universe).
-- t-stat is over runs, not rows (rows on one date are correlated).
with o as (
  select r.id run_id, r.scan_date, r.universe_id, t.tier, o.forward_return_pct fwd
  from signal_outcomes o
  join scan_runs r on r.id = o.run_id
  join ticker_results t on t.run_id = o.run_id and t.ticker = o.ticker
  where r.strategy_id = :'strategy' and o.horizon_days = :horizon
    and o.label_status = 'ok' and o.forward_return_pct is not null
), base as (
  select run_id, avg(fwd) u_mean from o group by run_id
), per_run as (
  select o.tier, o.run_id, count(*) n, avg(o.fwd) - b.u_mean spread,
         avg((o.fwd > b.u_mean)::int) beat_rate
  from o join base b using (run_id) group by o.tier, o.run_id, b.u_mean
)
select tier,
       count(*)                                   runs,
       sum(n)                                     rows,
       round(avg(spread)::numeric, 2)             mean_spread_pct,
       round((percentile_cont(0.5) within group (order by spread))::numeric, 2) median_spread_pct,
       round(avg(beat_rate)::numeric, 3)          beat_universe_rate,
       round((avg(spread) / nullif(stddev_samp(spread) / sqrt(count(*)), 0))::numeric, 2) t_over_runs
from per_run group by tier order by tier;
