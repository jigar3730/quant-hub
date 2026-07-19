# Quant Hub Architecture Gaps

**Baseline:** Launchpad technical scanner + ML and Lynch fundamentals
**Status:** Living risk register
**Last updated:** 2026-07-19

## Current architecture

```text
cron + Streamlit dashboard + Launchpad/Lynch CLIs
                     │
                     ├── Yahoo Finance / price cache
                     └── PostgreSQL → dashboard, digests, ML labels/models
```

The single `quant-hub` container hosts cron, dashboard, and product CLIs. `quant-hub-db` stores scan results, labels, model registry, and job audit records. Scheduled flow is weekday Launchpad, Saturday Launchpad coverage, Lynch coverage, Launchpad labeling, analytics, and digests. `docker/crontab` is authoritative.

Implemented controls include parameterized SQL, same-day upsert idempotency, Postgres health checking, product-specific ticker history, cache support, point-in-time Launchpad backfill, forward labels, and job audit records.

## High-priority gaps

| ID | Gap | Evidence | Recommended remediation |
|---|---|---|---|
| C1 | Dashboard has no built-in authentication and is published on host port 5002 | Compose/entrypoint/dashboard | Put it behind authenticated reverse proxy or VPN; do not expose it publicly |
| C2 | Postgres has a host port and a weak compose password fallback | Compose and default DSN | Require strong secrets; remove fallback; bind DB to internal network where possible |
| H1 | Scheduled failures are primarily log-only | Cron redirects to `cron.log`; app container lacks healthcheck | Alert on stale/failing runs, make schema init fail clearly, add application healthcheck |
| H2 | Backups are documented but not automated or restore-tested | Runbook manual `pg_dump` | Schedule backups, off-host copy, retention, and restore drills |
| H3 | No versioned schema migration system | Idempotent bootstrap SQL | Adopt numbered migrations and a schema-version record |
| H4 | `job_runs` cannot fully represent degraded data or email failures | Product services/job audit | Record partial/degraded outcomes and align status with exit/email result |
| H5 | Secrets are propagated into cron environment; container runs as root | Dockerfile and entrypoint | Use non-root runtime and restricted secret handling |
| H6 | No CI for lint, unit tests, schema, or Docker contract | Repository configuration | Add CI with Postgres-backed integration coverage |

## Product and data gaps

| ID | Gap | Effect | Recommended remediation |
|---|---|---|---|
| P1 | Yahoo is the sole market/fundamental provider | Rate limits and incomplete Lynch rows can affect scans | Expose data quality, retry with backoff, and add a secondary provider/circuit breaker |
| P2 | Launchpad ML has no live inference | Models currently tune research thresholds only | Require reproducible evaluation and explicit approval before adding a live reranker |
| P3 | Historical universes are not point-in-time membership sets | Backtests can have survivorship bias | Archive membership snapshots before broad ML claims |
| P4 | Scan history and JSONB payloads have no automated retention | Storage growth; destructive cleanup risk | Archive before purge and require confirmation for destructive operations |
| P5 | Launchpad∩Lynch is a combined research signal, not a measured portfolio | Risk of over-interpreting overlap | Track labeled outcomes and compare against product-only baselines |

## Engineering gaps

- No structured metrics, tracing, or alerting; operators must inspect logs and `quant-hub status`.
- No job lock prevents overlapping manual and cron scans.
- Cache freshness can diverge from persisted scan snapshots; show `as_of_price` and cache age.
- Dynamic ticker values should be validated and escaped before dashboard HTML rendering.
- Dependency versions are lower-bounded rather than locked; container bootstrap supply chain should be pinned.
- Email delivery needs retry/backoff and an explicit degraded status.

## Remediation order

1. Restrict dashboard/Postgres exposure and remove weak secret defaults.
2. Automate backups, failure alerts, health checks, and restore tests.
3. Add schema migrations, CI, structured telemetry, and container hardening.
4. Add job locking, retention/archive policy, point-in-time universes, and data-provider resilience.
5. Validate Launchpad ML and overlap outcomes before increasing automation.

See [Runbook](RUNBOOK.md) for current operations and [Data Model](DATA_MODEL.md) for the persistence model.
